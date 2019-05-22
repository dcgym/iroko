from __future__ import print_function
import argparse
import os
import glob
import random
import json
import time

# Ray imports
import ray
from ray.rllib.agents.registry import get_agent_class
from ray.rllib.agents.trainer import Trainer, with_common_config
from ray.tune.registry import register_env
import ray.tune as tune
from ray.tune.experiment import Experiment
from ray.tune.schedulers import PopulationBasedTraining
# Iroko imports
import dc_gym
import dc_gym.utils as dc_utils

# configure logging
import logging
log = logging.getLogger(__name__)

# set up paths
cwd = os.getcwd()
lib_dir = os.path.dirname(dc_gym.__file__)
INPUT_DIR = lib_dir + '/inputs'
ROOT_OUTPUT_DIR = cwd + '/results'


class MaxAgent(Trainer):
    """Agent that always takes the maximum available action."""
    _agent_name = "MaxAgent"
    _default_config = with_common_config({})

    def _init(self, config, env_creator):
        self.config = config
        self.env = env_creator(config["env_config"])
        self.env.reset()

    def _name(self):
        return self._agent_name

    def _train(self):
        steps = 0
        done = False
        reward = 0.0
        while not done:
            action = self.env.action_space.high
            obs, r, done, info = self.env.step(action)
            reward += r
            steps += 1
            if steps >= self.config["env_config"]["iterations"]:
                done = True
        return {
            "episode_reward_mean": reward,
            "timesteps_this_iter": steps,
        }


class RandomAgent(Trainer):
    """Agent that always takes the maximum available action."""
    _agent_name = "RandomAgent"
    _default_config = with_common_config({})

    def _init(self, config, env_creator):
        self.env = env_creator(config["env_config"])
        self.env.reset()

    def _name(self):
        return self._agent_name

    def _train(self):
        steps = 0
        done = False
        reward = 0.0
        while not done:
            action = self.env.action_space.sample()
            obs, r, done, info = self.env.step(action)
            reward += r
            steps += 1
            if steps >= self.config["env_config"]["iterations"]:
                done = True
        return {
            "episode_reward_mean": reward,
            "timesteps_this_iter": steps,
        }


def get_env(env_config):
    return dc_utils.EnvFactory.create(env_config)


def get_gym(env_config):
    import gym
    iterations = env_config["iterations"]
    gym.register(id='dc-iroko-v0',
                 entry_point='dc_gym.env_iroko:DCEnv',
                 max_episode_steps=iterations,
                 )
    env = gym.make('dc-iroko-v0', conf=env_config)
    return env


def set_tuning_parameters(agent, config):
    scheduler = None
    if agent.lower() == "ppo":
        # Postprocess the perturbed config to ensure it's still valid
        def explore(config):
            # ensure we collect enough timesteps to do sgd
            if config["train_batch_size"] < config["sgd_minibatch_size"] * 2:
                config["train_batch_size"] = config["sgd_minibatch_size"] * 2
            # ensure we run at least one sgd iter
            if config["num_sgd_iter"] < 1:
                config["num_sgd_iter"] = 1
            return config
        # optimization related parameters
        # hype_params["kl_coeff"] = lambda: random.uniform(.1, .8)
        # hype_params["entropy_coeff"] = lambda: random.uniform(0.0, 1.0)
        # hype_params["kl_target"] = lambda: random.uniform(0.0, 0.05)
        hype_params = {
            "lambda": lambda: random.uniform(0.9, 1.0),
            "clip_param": lambda: random.uniform(0.01, 0.5),
            "lr": [1e-3, 5e-4, 1e-4, 5e-5, 1e-5],
            "num_sgd_iter": lambda: random.randint(1, 30),
            "sgd_minibatch_size": lambda: random.randint(128, 16384),
            "train_batch_size": lambda: random.randint(2000, 160000),
        }
        config["num_sgd_iter"] = tune.sample_from(
            lambda spec: random.choice([10, 20, 30])),
        config["sgd_minibatch_size"] = tune.sample_from(
            lambda spec: random.choice([128, 512, 2048])),
        config["train_batch_size"] = tune.sample_from(
            lambda spec: random.choice([10000, 20000, 40000]))
        scheduler = PopulationBasedTraining(time_attr="time_total_s",
                                            reward_attr="episode_reward_mean",
                                            perturbation_interval=120,
                                            resample_probability=0.25,
                                            hyperparam_mutations=hype_params,
                                            custom_explore_fn=explore)

    if agent.lower() == "ddpg":
        pass

    if agent.lower() == "pg":
        pass

    return config, scheduler


def get_agent(agent_name):

    if agent_name.lower() == "rnd":
        agent_class = type(agent_name.upper(), (RandomAgent,), {})
        return agent_class
    try:
        agent_class = get_agent_class(agent_name.upper())
    except Exception as e:
        log.info("%s Loading basic algorithm" % e)
        # We use PG as the base class for experiments
        agent_class = type(agent_name.upper(), (MaxAgent,), {})
    return agent_class


def get_tune_experiment(config, agent, timesteps, root_dir):
    SCHEDULE = False
    scheduler = None
    agent_class = get_agent(agent)
    ex_conf = {}
    ex_conf["name"] = agent
    ex_conf["run"] = agent_class
    ex_conf["local_dir"] = root_dir
    ex_conf["stop"] = {"timesteps_total": timesteps}

    if SCHEDULE:
        ex_conf["stop"] = {"time_total_s": timesteps / 2}
        ex_conf["num_samples"] = 2
        config["env_config"]["parallel_envs"] = True
        # custom changes to experiment
        log.info("Performing tune experiment")
        config, scheduler = set_tuning_parameters(agent, config)
    ex_conf["config"] = config
    experiment = Experiment(**ex_conf)
    return experiment, scheduler


def configure_ray(args):
    # Load the config specific to the agent
    try:
        with open("%s/ray_configs/%s.json" % (cwd, args.agent), 'r') as fp:
            config = json.load(fp)
    except IOError:
        # File does not exist, just initialize an empty configuration.
        log.info("Agent configuration does not exist, starting with default.")
        config = {}
    # Add the dynamic environment configuration
    config["env"] = "dc_env"
    config["clip_actions"] = True
    config["num_workers"] = 1
    config["num_gpus"] = 0
    # config["batch_mode"] = "truncate_episodes"
    config["log_level"] = "ERROR"

    config["env_config"] = {
        "input_dir": INPUT_DIR,
        "output_dir": args.root_output + "/" + args.agent,
        "env": args.env,
        "topo": args.topo,
        "agent": args.agent,
        "transport": args.transport,
        "iterations": args.timesteps,
        "tf_index": args.pattern_index,
        "topo_conf": {},
    }

    # customized configurations
    if args.agent.lower() == "td3":
        config["twin_q"] = True
        config['env_config']['agent'] = "ddpg"
    if args.agent.lower() == "apex_ddpg":
        if config["num_workers"] < 2:
            config["num_workers"] = 2

    if args.agent.lower() == "a3c":
        config["env_config"]["parallel_envs"] = True

    if config["num_workers"] > 1:
        config["env_config"]["parallel_envs"] = True
    if args.timesteps > 50000:
        config["env_config"]["sample_delta"] = int(args.timesteps / 50000)
    return config


def run(config, timesteps):
    agent_class = get_agent(config["env_config"]["agent"])
    agent = agent_class(config=config, env="dc_env")
    steps = 0
    while steps < timesteps:
        output = agent.train()
        steps += output["timesteps_this_iter"]
        log.info("Current timesteps %d" % steps)
    log.info("Generator Finished. Simulation over. Clearing dc_env...")


def tune_run(config, timesteps, root_dir):
    agent = config['env_config']['agent']
    experiment, scheduler = get_tune_experiment(
        config, agent, timesteps, root_dir)
    tune.run(experiment, config=config, scheduler=scheduler, verbose=1)
    log.info("Tune run over. Clearing dc_env...")


def check_file(pattern):
    for fname in glob.glob(pattern, recursive=True):
        if os.path.isfile(fname):
            return True
    return False


def kill_ray():
    dc_utils.kill_processes_with_name("ray_")
    if dc_utils.list_processes("ray_"):
        # Show 'em who's boss
        dc_utils.kill_processes_with_name("ray_", use_sigkill=True)


def clean():
    ''' A big fat hammer to get rid of all the debris left over by ray '''
    log.info("Removing all previous traces of Mininet and ray")
    kill_ray()
    os.system('sudo mn -c')
    dc_utils.kill_processes_with_name("goben")
    dc_utils.kill_processes_with_name("node_control")


def wait_for_ovs():
    import subprocess
    ovs_cmd = "ovs-vsctl --timeout=10 list-br"
    timeout = 60
    while True:
        result = subprocess.run(ovs_cmd.split(), stdout=subprocess.PIPE)
        if result.stdout == b'':
            break
        # time out after 60 seconds and clean up...
        if timeout == 0:
            log.error("Timed out! Swinging the cleaning hammer...")
            clean()
            return
        log.info("Timing out in %d..." % timeout)
        time.sleep(1)
        timeout -= 1


def get_args(args=None):
    p = argparse.ArgumentParser()
    p.add_argument('--env', '-e', dest='env',
                   default='iroko', help='The platform to run.')
    p.add_argument('--topo', dest='topo',
                   default='dumbbell', help='The topology to operate on.')
    p.add_argument('--num_hosts', dest='num_hosts',
                   default='4', help='The number of hosts in the topology.')
    p.add_argument('--agent', '-a', dest='agent', default="PG",
                   help='must be string of either: PPO, DDPG, PG,'
                   ' DCTCP, TCP_NV, PCC, or TCP', type=str.lower)
    p.add_argument('--timesteps', '-t', dest='timesteps',
                   type=int, default=10000,
                   help='total number of timesteps to train rl agent, '
                   'if tune specified is wall clock time')
    p.add_argument('--pattern', '-p', dest='pattern_index',
                   type=int, default=0,
                   help='Traffic pattern we are testing.')
    p.add_argument('--checkpoint_freq', '-cf', dest='checkpoint_freq',
                   type=int, default=0,
                   help='how often to checkpoint model')
    p.add_argument('--restore', '-r', dest='restore', default=None,
                   help='Path to checkpoint to restore (for testing), must '
                   'end like this: <path>/checkpoint-* where star is the '
                        'check point number')
    p.add_argument('--output', dest='root_output', default=ROOT_OUTPUT_DIR,
                   help='Folder which contains all the collected metrics.')
    p.add_argument('--transport', dest='transport', default="udp",
                   help='Choose the transport protocol of the hosts.')
    p.add_argument('--tune', action="store_true", default=False,
                   help='Specify whether to perform hyperparameter tuning')
    return p.parse_args(args)


def main(args=None):
    logging.basicConfig(format="%(levelname)s:%(message)s",
                        level=logging.INFO)
    args = get_args(args)
    if args is None:
        log.error("Something went wrong while parsing arguments!")
        exit(1)

    log.info("Registering the DC environment...")
    register_env("dc_env", get_env)
    # Configure all ray input parameters based on the arguments
    config = configure_ray(args)
    output_dir = config["env_config"]["output_dir"]
    # Check if the output directory exists before running
    dc_utils.check_dir(output_dir)
    # Dump the configuration
    dc_utils.dump_json(path=output_dir, name="ray_config", data=config)

    log.info("Starting Ray...")
    ts = time.time()
    ray.init(ignore_reinit_error=True,
             logging_level=logging.WARN,
             temp_dir=output_dir,
             plasma_store_socket_name="/tmp/plasma_socket%s" % ts,
             raylet_socket_name="/tmp/raylet_socket%s" % ts)

    log.info("Starting experiment.")
    if args.tune:
        tune_run(config, args.timesteps, args.root_output)
    else:
        run(config, args.timesteps)

    # Wait until the topology is torn down completely
    # The flaky Mininet stop() call necessitates this
    # This is an unfortunate reality and may conflict with other ovs setups
    log.info("Waiting for environment to complete...")
    wait_for_ovs()
    # Take control back from root
    dc_utils.change_owner(args.root_output)
    # Ray doesn't play nice and prevents proper shutdown sometimes
    ray.shutdown()
    # time.sleep(1)
    # kill_ray()
    log.info("Experiment has completed.")


if __name__ == '__main__':
    main()
