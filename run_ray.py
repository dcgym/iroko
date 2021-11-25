import argparse
import os
import random
import json
import time
import subprocess

# configure logging
import logging
# Ray imports
import ray
from ray.rllib.agents.registry import get_trainer_class
from ray.rllib.agents.trainer import Trainer, with_common_config
from ray.rllib.utils.annotations import override
from ray.rllib.utils.typing import TrainerConfigDict
from ray.tune.registry import register_env
import ray.tune as tune
from ray.tune.experiment import Experiment
from ray.tune.schedulers import PopulationBasedTraining

log = logging.getLogger(__name__)

# Iroko imports
import dc_gym.utils as dc_utils
import dc_gym

# set up paths
cwd = os.getcwd()
lib_dir = os.path.dirname(dc_gym.__file__)
INPUT_DIR = lib_dir + '/inputs'
ROOT_OUTPUT_DIR = cwd + '/results'


class MaxAgent(Trainer):
    """Agent that always takes the maximum available action."""
    _name = "MaxAgent"
    _default_config = with_common_config({})

    @classmethod
    # @override(Trainer)
    def get_default_config(cls) -> TrainerConfigDict:
        return with_common_config({})

    @override(Trainer)
    def _init(self, config, env_creator):
        self.config = config
        self.env = env_creator(config["env_config"])

    @override(Trainer)
    def step(self):
        rewards = []
        steps = 0
        obs = self.env.reset()
        done = False
        reward = 0.0
        while not done:
            action = self.env.action_space.high
            obs, r, done, info = self.env.step(action)
            reward += r
            steps += 1
        rewards.append(reward)
        return {
            "episode_reward_mean": sum(rewards) / len(rewards),
            "agent_timesteps_total": steps,
            "episodes_this_iter": 1,
        }

    @override(Trainer)
    def cleanup(self):
        # TODO: Create workers so that we do not have to call cleanup manually.
        if self.env is not None:
            self.env.close()


class RandomAgent(Trainer):
    """Agent that always takes the maximum available action."""
    _name = "RandomAgent"
    _default_config = with_common_config({})

    @classmethod
    # @override(Trainer)
    def get_default_config(cls) -> TrainerConfigDict:
        return with_common_config({
        })

    @override(Trainer)
    def _init(self, config, env_creator):
        self.config = config
        self.env = env_creator(config["env_config"])

    @override(Trainer)
    def step(self):
        rewards = []
        steps = 0
        obs = self.env.reset()
        done = False
        reward = 0.0
        while not done:
            action = self.env.action_space.sample()
            obs, r, done, info = self.env.step(action)
            reward += r
            steps += 1
        rewards.append(reward)
        return {
            "episode_reward_mean": sum(rewards) / len(rewards),
            "agent_timesteps_total": steps,
            "episodes_this_iter": 1,
        }

    @override(Trainer)
    def cleanup(self):
        # TODO: Create workers so that we do not have to call cleanup manually.
        if self.env is not None:
            self.env.close()


def get_env(env_config):
    return dc_utils.EnvFactory.create(env_config)


def get_gym(env_config):
    import gym
    iterations = env_config["iterations"]
    gym.register(
        id='dc-iroko-v0',
        entry_point='dc_gym.env_iroko:DCEnv',
        max_episode_steps=iterations,
    )
    env = gym.make('dc-iroko-v0', conf=env_config)
    return env


def set_tuning_parameters(agent, config):
    scheduler = None
    if agent.lower() == "ppo":

        def explore(config):
            config["train_batch_size"] = max(config["train_batch_size"],
                                             2000)  # should be 4 at minimum
            if config["train_batch_size"] < config["sgd_minibatch_size"] * 2:
                config["train_batch_size"] = config["sgd_minibatch_size"] * 2
            # ensure we run at least one sgd iter
            if config["num_sgd_iter"] < 1:
                config["num_sgd_iter"] = 1
            if config['horizon'] < 32:
                config['horizon'] = 32
            for k in config.keys():
                if k == 'use_gae':
                    continue  # that one is fine and also non numeric
                if config[k] < 0.0:
                    # this...is a lazy way to make sure things are at worse 0
                    config[k] = 0.0
            return config

        hyper_params = {
            # update frequency
            "horizon": random.randint(10000, 50000),
            "sgd_minibatch_size": random.randint(128, 16384),
            "train_batch_size": random.randint(2000, 160000),
            "num_sgd_iter": random.randint(3, 30),
            # Objective hyperparams:
            # "clip_param": random.uniform(0.01, 0.5),
            # "kl_target": random.uniform(0.003, 0.03),
            # "kl_coeff": random.uniform(0.3, 1),
            # "use_gae": random.choice([True, False]),
            # "gamma": random.choice([0.99,
            #                        random.uniform(0.8, 0.9997),
            #                        random.uniform(0.8, 0.9997)]),
            # "lambda": random.uniform(0.9, 1.0),

            # val fn & entropy coeff
            # "vf_loss_coeff": random.choice([0.5, 1.0]),
            # "entropy_coeff": random.uniform(0, 0.01),
            # "lr": random.uniform(5e-6, 0.003),
        }
        # creates a wide range of the potential population
        for k in hyper_params.keys():
            config[k] = tune.sample_from(lambda spec: hyper_params[k])
        scheduler = PopulationBasedTraining(time_attr="time_total_s",
                                            reward_attr="episode_reward_mean",
                                            perturbation_interval=120,
                                            resample_probability=0.80,
                                            hyperparam_mutations=hyper_params,
                                            custom_explore_fn=explore)

    if agent.lower() == "ddpg":
        pass

    if agent.lower() == "pg":
        pass

    return config, scheduler


def get_agent(agent_name):

    if agent_name.lower() == "rnd":
        agent_class = type(agent_name.upper(), (RandomAgent, ), {})
        return agent_class
    try:
        agent_class = get_trainer_class(agent_name.upper())
    except Exception as e:
        log.info("%s Loading basic algorithm", e)
        # We use MaxAgent as the base class for experiments
        agent_class = type(agent_name.upper(), (MaxAgent, ), {})
    return agent_class


def get_tune_experiment(config, agent, episodes, root_dir, is_schedule):
    scheduler = None
    agent_class = get_agent(agent)
    ex_conf = {}
    ex_conf["name"] = agent
    ex_conf["run"] = agent_class
    ex_conf["local_dir"] = config["env_config"]["output_dir"]
    ex_conf["stop"] = {"episodes_total": episodes}

    if is_schedule:
        ex_conf["stop"] = {"time_total_s": 300}
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
        log.info(
            "Agent configuration for \"%s\" does not exist," +
            " starting with default.", args.agent)
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
        "tf_index": args.pattern_index,
        "topo_conf": {
            "max_capacity": args.rate * 1e6
        },
    }

    # customized configurations
    if args.agent.lower() == "td3":
        config["twin_q"] = True
        config['env_config']['agent'] = "ddpg"
    if args.agent.lower().startswith("apex") or config.get("sample_async"):
        if config["num_workers"] < 2:
            config["num_workers"] = 2

    if args.agent.lower() == "a3c":
        config["env_config"]["parallel_envs"] = True

    if config["num_workers"] > 1:
        config["env_config"]["parallel_envs"] = True
    return config


def run_ray(config, total_episodes):
    agent_class = get_agent(config["env_config"]["agent"])
    agent = agent_class(config=config, env="dc_env")
    steps = 0
    episodes = 0
    while episodes < total_episodes:
        output = agent.train()
        steps = output["agent_timesteps_total"]
        episodes += output["episodes_this_iter"]
        log.info("Episode: %d Total timesteps: %d", episodes, steps)
    log.info("Generator Finished. Simulation over. Clearing dc_env...")
    agent.cleanup()


def tune_run(config, episodes, root_dir, is_schedule):
    agent = config['env_config']['agent']
    experiment, scheduler = get_tune_experiment(config, agent, episodes,
                                                root_dir, is_schedule)
    tune.run(experiment, config=config, scheduler=scheduler, verbose=2)
    log.info("Tune run over. Clearing dc_env...")


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
    dc_utils.kill_processes_with_name("go_ctrl")
    dc_utils.kill_processes_with_name("node_control")


def wait_for_ovs():
    ovs_cmd = "ovs-vsctl --timeout=10 list-br"
    timeout = 30
    while True:
        result = subprocess.run(ovs_cmd.split(), stdout=subprocess.PIPE)
        if result.stdout == b'':
            break
        # time out after 60 seconds and clean up...
        if timeout == 0:
            log.error("Timed out! Swinging the cleaning hammer...")
            clean()
            return
        log.info("Timing out in %d...", timeout)
        time.sleep(1)
        timeout -= 1


def get_args(args=None):
    p = argparse.ArgumentParser()
    p.add_argument('--topo',
                   '-t',
                   dest='topo',
                   type=str.lower,
                   default='dumbbell',
                   help='The topology to operate on.')
    p.add_argument('--num_hosts',
                   dest='num_hosts',
                   type=int,
                   default='4',
                   help='The number of hosts in the topology.')
    p.add_argument('--agent',
                   '-a',
                   dest='agent',
                   default="PG",
                   type=str.lower,
                   help='must be string of either: PPO, DDPG, PG,'
                   ' DCTCP, TCP_NV, PCC, or TCP')
    p.add_argument('--episodes',
                   '-e',
                   dest='episodes',
                   type=int,
                   default=2,
                   help='Total number of episodes to train the RL agent.')
    p.add_argument('--iterations',
                   '-i',
                   dest='timesteps',
                   type=int,
                   default=10000,
                   help='Total number of episodes to train the RL agent.')
    p.add_argument('--pattern',
                   '-p',
                   dest='pattern_index',
                   type=int,
                   default=0,
                   help='Traffic pattern we are testing.')
    p.add_argument('--rate',
                   '-r',
                   dest='rate',
                   default=10,
                   type=int,
                   help='Maximum bandwidth in mbit that each link supports. ')
    p.add_argument('--output',
                   dest='root_output',
                   default=ROOT_OUTPUT_DIR,
                   help='Folder which contains all the collected metrics.')
    p.add_argument('--env',
                   dest='env',
                   type=str.lower,
                   default='iroko',
                   help='The platform to run.')
    p.add_argument('--transport',
                   dest='transport',
                   default="udp",
                   type=str.lower,
                   help='The transport protocol of the hosts.')
    p.add_argument('--tune',
                   action="store_true",
                   default=False,
                   help='Specify whether to run the tune framework')
    p.add_argument('--schedule',
                   action="store_true",
                   default=False,
                   help='Specify whether to perform hyperparameter tuning')
    return p.parse_args(args)


def main(args=None):
    # Fix a bug introduced by an annoying Google extension
    import absl.logging
    try:
        logging.root.removeHandler(absl.logging._absl_handler)
        absl.logging._warn_preinit_stderr = False
    except Exception as e:
        print("Failed to fix absl logging bug", e)

    logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)
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
    dc_utils.check_dir("/tmp/ray_plasma")
    log.info("Starting Ray...")
    # We need to save to tmp with ray because the path names are too long.
    tmp_dir = "/tmp/ray"
    ray.init(ignore_reinit_error=True,
             logging_level=logging.INFO,
             _temp_dir=tmp_dir)

    log.info("Starting experiment.")
    try:
        if args.tune:
            tune_run(config, args.episodes, args.root_output, args.schedule)
        else:
            run_ray(config, args.episodes)
    except Exception as ex:
        log.error("%s: %s", type(ex).__name__, ex)

    # Wait until the topology is torn down completely
    # The flaky Mininet stop() call necessitates this
    # This is an unfortunate reality and may conflict with other ovs setups
    log.info("Waiting for environment to complete...")
    wait_for_ovs()
    # Take control back from root
    dc_utils.change_owner(args.root_output)
    # Ray doesn't play nice and prevents proper shutdown sometimes
    ray.shutdown()
    log.info("Experiment has completed.")


if __name__ == '__main__':
    main()
