from __future__ import print_function
import argparse
import os

# Ray imports
import ray
from ray.tune.registry import register_env
from ray.rllib.agents import ppo, ddpg, pg
import ray.tune as tune
from ray.tune.schedulers import PopulationBasedTraining
import random

# Iroko imports
import dc_gym
from dc_gym.factories import EnvFactory

# set up paths
cwd = os.getcwd()
lib_dir = os.path.dirname(dc_gym.__file__)
INPUT_DIR = lib_dir + '/inputs'
OUTPUT_DIR = cwd + '/results'
SEEDS = 2

PARSER = argparse.ArgumentParser()
PARSER.add_argument('--env', '-e', dest='env',
                    default='iroko', help='The platform to run.')
PARSER.add_argument('--topo', '-to', dest='topo',
                    default='dumbbell', help='The topology to operate on.')
PARSER.add_argument('--agent', '-a', dest='agent', default=None,
                    help='must be string of either: PPO, DDPG, PG,'
                         ' DCTCP, TCP_NV or TCP')
PARSER.add_argument('--timesteps', '-t', dest='timesteps',
                    type=int, default=10000,
                    help='total number of timesteps to train rl agent, '
                         'if tune specified is wall clock time')
PARSER.add_argument('--checkpoint_freq', '-cf', dest='checkpoint_freq',
                    type=int, default=0,
                    help='how often to checkpoint model')
PARSER.add_argument('--restore', '-r', dest='restore', default=None,
                    help='Path to checkpoint to restore (for testing), must '
                    'end like this: <path>/checkpoint-* where star is the '
                    'check point number')
PARSER.add_argument('--output', dest='output_dir', default=OUTPUT_DIR,
                    help='Folder which contains all the collected metrics.')
PARSER.add_argument('--transport', dest='transport', default="udp",
                    help='Choose the transport protocol of the hosts.')
PARSER.add_argument('--tune', dest='tune', type=bool, default=False,
                    help='Specify whether to perform hyperparameter tuning')
ARGS = PARSER.parse_args()


def get_env(env_config):
    return EnvFactory.create(env_config)


def ppo_explore(config):
    # ensure we collect enough timesteps to do sgd
    if config["train_batch_size"] < config["sgd_minibatch_size"] * 2:
        config["train_batch_size"] = config["sgd_minibatch_size"] * 4
    # ensure we run at least one sgd iter
    if config["num_sgd_iter"] < 1:
        config["num_sgd_iter"] = 1
    if config["lr"] <= 0.0:
        config["lr"] = 1e-3
    # just in case any of these values go negative...which isn't ok as is
    for k in config.keys():

        if config[k] < 0.0:
            config[k] = 0.0

    return config


def set_tuning_parameters(agent, config):
    hype_params = {}
    explore = None
    if agent == "PPO":
        # optimization related parameters
        hype_params["lr"] = [
            float(1e-2), float(1e-3), float(1e-4), float(1e-5)]
        hype_params["train_batch_size"] = [1000, 2000, 4000]
        hype_params["sgd_minibatch_size"] = [16, 32, 64, 128]
        hype_params["num_sgd_iter"] = lambda: random.randint(1, 30)
        hype_params["lambda"] = lambda: random.random()  # GAE param
        # initial coeff of KL term
        hype_params["kl_coeff"] = lambda: random.uniform(.1, .8)
        # size of clipping in PPO term
        hype_params["clip_param"] = lambda: random.uniform(.1, .8)
        hype_params["entropy_coeff"] = lambda: random.uniform(
            0.0, 1.0)  # entropy coeff
        hype_params["kl_target"] = lambda: random.uniform(
            0.0, 0.05)  # .1 might be a bit high
        explore = ppo_explore

    for k in hype_params.keys():
        # just to give some variation at start
        if isinstance(hype_params[k], list) and not (k == 'lr'):
            if k == 'train_batch_size':
                config[k] = lambda spec: random.choice([1000, 2000, 4000])
            if k == 'sgd_minibatch_size':
                config[k] = lambda spec: random.choice([16, 32, 64, 128])

    return config, hype_params, explore


def clean():
    ''' A big fat hammer to get rid of all the debris left over by ray '''
    print ("Removing all previous traces of Mininet and ray")
    ray_kill = "sudo kill -9 $(ps aux | grep 'ray/workers' | awk '{print $2}')"
    os.system(ray_kill)
    os.system('sudo mn -c')
    os.system("sudo killall -9 goben")
    os.system("sudo killall -9 node_control")


def configure(agent):
    if ARGS.tune:
        name = "%s_tune_experiment" % agent
    else:
        name = "%s_experiment" % agent
    config = {}
    scheduler = None
    experiment = {
        name: {
            'local_dir': ARGS.output_dir,
            "stop": {"timesteps_total": ARGS.timesteps},
            "env": "dc_env",
            "checkpoint_freq": ARGS.checkpoint_freq,
            "checkpoint_at_end": True,
            "restore": ARGS.restore
        }
    }

    if agent == "PPO":
        experiment[name]["run"] = agent
        config = ppo.DEFAULT_CONFIG.copy()
        config["train_batch_size"] = 4000
        # TODO this number should be like 4k, 8k, 16k, etc.
        # config based on paper: "Proximal Policy Optimization Algrothm"
        # Specifically experiment 6.1
        config['model']['fcnet_hiddens'] = [400, 300]
        config['model']['fcnet_activation'] = 'tanh'
        config["train_batch_size"] = 4000
        config['horizon'] = 2048
        config['lambda'] = 0.95
        config['sgd_minibatch_size'] = 64
        config['num_sgd_iter'] = 10  # assuming this is epochs...
        config['lr'] = 3e-4
        # use only clip objective as paper found this worked best
        # TODO: pick these vals specific for data centers
        # config['kl_target'] = 0.0
        config['clip_param'] = 0.2
        config['kl_coeff'] = 0.0
        if ARGS.tune and agent == "PPO":
            # changes to experiment
            print("Performing tune experiment")
            experiment[name]["stop"] = {"time_total_s": ARGS.timesteps / 2}
            experiment[name]["num_samples"] = SEEDS
            config, mutations, explore = set_tuning_parameters(
                agent, config.copy())
            config['horizon'] = 1000
            scheduler = PopulationBasedTraining(time_attr='time_total_s',
                                                reward_attr='episode_reward_mean',
                                                perturbation_interval=5000,  # this..will be pretty sparse
                                                hyperparam_mutations=mutations,
                                                resample_probability=0.25,
                                                custom_explore_fn=explore)
    elif agent == "DDPG":
        experiment[name]["run"] = agent
        config = ddpg.DEFAULT_CONFIG.copy()
        config["actor_hiddens"] = [400, 300]
        config["actor_hidden_activation"] = "relu"
        config["critic_hiddens"] = [400, 300]
        config["critic_hidden_activation"] = "relu"
        config["tau"] = 0.001
        config["noise_scale"] = 1.0
        config["l2_reg"] = 1e-2
        config["train_batch_size"] = 64
        config["exploration_fraction"] = 0.3
        config["prioritized_replay"] = False
        config["lr"] = 1e-3
        config["actor_loss_coeff"] = 0.1
        config["critic_loss_coeff"] = 1.0

    else:  # the rest of the experiments just runs PG
        experiment[name]["run"] = "PG"
        config = pg.DEFAULT_CONFIG.copy()
        # TODO need to be able to save, work around for now
        experiment[name].pop("checkpoint_freq", None)
        experiment[name].pop("restore", None)

    config['clip_actions'] = True
    config['num_workers'] = 0
    config["batch_mode"] = "truncate_episodes"
    config['env_config'] = {
        "input_dir": INPUT_DIR,
        "output_dir": ARGS.output_dir,
        "env": ARGS.env,
        "topo": ARGS.topo,
        "agent": ARGS.agent,
        "transport": ARGS.transport,
        "tf_index": 0,
    }

    experiment[name]["config"] = config
    return experiment, scheduler


def init():
    print("Registering the DC environment...")
    register_env("dc_env", get_env)

    print("Starting Ray...")
    ray.init(num_cpus=1)

    print("Starting experiment.")
    experiment, scheduler = configure(ARGS.agent)
    tune.run_experiments(experiment, scheduler=scheduler)
    print("Experiment has completed.")


if __name__ == '__main__':
    init()
