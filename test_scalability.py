from __future__ import print_function
from __future__ import division  # For Python 2
import numpy as np
import pandas as pd
from filelock import FileLock
import os
import logging
import time
# Ray imports
import ray
from ray.rllib.agents.registry import get_agent_class
from ray.rllib.agents.agent import Agent, with_common_config
from ray.tune.registry import register_env
import ray.tune as tune
# Iroko imports
import dc_gym
from dc_gym.factories import EnvFactory
# Fixed matplotlib import
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns


PLOT_DIR = os.path.dirname(os.path.abspath(__file__)) + "/plots"

# These commands might help with scaling out the machine. After inserting
# reboot the machine.

# echo "* soft nofile 1048576" >> /etc/security/limits.conf
# echo "* hard nofile 1048576" >> /etc/security/limits.conf
# echo "* soft nproc unlimited" >> /etc/security/limits.conf
# echo "* hard nproc unlimited" >> /etc/security/limits.conf
# echo "* soft stack unlimited" >> /etc/security/limits.conf
# echo "* hard stack unlimited" >> /etc/security/limits.conf
# echo "kernel.threads-max = 2091845" >> /etc/sysctl.conf
# echo "kernel.pty.max = 210000" >> /etc/sysctl.conf
# echo "DefaultTasksMax=infinity" >> /etc/systemd/system.conf
# echo "UserTasksMax=infinity" >> /etc/systemd/logind.conf
# sysctl -p
# systemctl daemon-reload
# systemctl daemon-reexec

# set up paths
cwd = os.getcwd()
lib_dir = os.path.dirname(dc_gym.__file__)
INPUT_DIR = lib_dir + '/inputs'
OUTPUT_DIR = cwd + '/scalability_test'


class MaxAgent(Agent):
    """Agent that always takes the maximum available action."""
    _agent_name = "MaxAgent"
    _default_config = with_common_config({})

    def _init(self):
        self.env = self.env_creator(self.config["env_config"])
        self.env.reset()

    def _train(self):
        steps = 0
        done = False
        reward = 0.0
        max_iterations = self.config["env_config"]["iterations"]
        while steps < max_iterations:
            action = self.env.action_space.high
            obs, r, done, info = self.env.step(action)
            reward += r
            steps = steps + 1
        return {
            "episode_reward_mean": reward,
            "timesteps_this_iter": steps,
        }


def check_dir(directory):
    # create the folder if it does not exit
    if not directory == '' and not os.path.exists(directory):
        print("Folder %s does not exist! Creating..." % directory)
        os.makedirs(directory)


def get_env(env_config):
    return EnvFactory.create(env_config)


def get_agent(agent_name):
    try:
        agent_class = get_agent_class(agent_name.upper())
    except Exception as e:
        print("%s Loading basic algorithm" % e)
        # We use PG as the base class for experiments
        agent_class = type(agent_name.upper(), (MaxAgent,), {})
    return agent_class


def get_tune_experiment(config, agent):
    scheduler = None
    name = "%s_tune" % agent
    agent_class = get_agent(agent)

    experiment = {
        name: {
            'run': agent_class,
            'local_dir': config['env_config']["output_dir"],
            "stop": {"timesteps_total": config['env_config']["iterations"]},
            "env": "dc_env",
        }
    }
    experiment[name]["config"] = config
    return experiment, scheduler


def configure_ray(num_hosts, tf_index):
    config = {}
    config['num_workers'] = 0
    config['num_gpus'] = 0
    config["batch_mode"] = "truncate_episodes"
    config["log_level"] = "ERROR"
    config['env_config'] = {
        "input_dir": INPUT_DIR,
        "output_dir": OUTPUT_DIR + "/%d_hosts" % num_hosts,
        "env": "iroko",
        "topo": "dumbbell",
        "agent": "TCP",
        "transport": "udp",
        "iterations": 1000,
        "tf_index": tf_index,
        "topo_conf": {"num_hosts": num_hosts, "parallel_envs": True},
    }
    return config


def tune_run(config):
    agent = config['env_config']['agent']
    experiment, scheduler = get_tune_experiment(config, agent)
    tune.run_experiments(experiment, scheduler=scheduler)


STATS_DICT = {"backlog": 0, "olimit": 1,
              "drops": 2, "bw_rx": 3, "bw_tx": 4}


def check_plt_dir(plt_name):
    plt_dir = os.path.dirname(plt_name)
    if not plt_dir == '' and not os.path.exists(plt_dir):
        print("Folder %s does not exist! Creating..." % plt_name)
        os.makedirs(plt_dir)


def plot_scalability_graph(increments, data_dir, plot_dir, name):
    bw_list = {}
    bw_list["rx"] = []
    bw_list["tx"] = []
    for increment in increments:
        stats_file = '%s/%s_hosts/runtime_statistics.npy' % (
            data_dir, increment)
        print("Loading %s..." % stats_file)
        with FileLock(stats_file + ".lock"):
            try:
                statistics = np.load(stats_file).item()
            except Exception:
                print("Error loading file %s" % stats_file)
                exit(1)
        port_stats = np.moveaxis(statistics["stats"], 0, -1)
        port_rx_bws = np.array(port_stats[STATS_DICT["bw_rx"]])
        port_tx_bws = np.array(port_stats[STATS_DICT["bw_tx"]])
        # bandwidths
        print("Computing mean of interface bandwidth per step.")
        bw_list["rx"].append(port_rx_bws.sum())
        bw_list["tx"].append(port_tx_bws.sum())
    # Set seaborn style for plotting
    sns.set(style="white", font_scale=1)
    bws_pd = pd.DataFrame.from_dict(bw_list)
    bws_pd.index = increments
    print (bws_pd)
    fig = sns.lineplot(data=bws_pd)
    fig.set_xticklabels(increments)
    fig.legend(loc='upper left')
    plt_name = "%s/" % (plot_dir)
    plt_name += "%s" % name
    print("Saving plot %s" % plt_name)
    check_plt_dir(plt_name)
    plt.savefig(plt_name + ".pdf")
    plt.savefig(plt_name + ".png")
    plt.gcf().clear()


def run(config):
    agent_class = get_agent(config["env_config"]["agent"])
    agent = agent_class(config=config, env="dc_env")
    agent.train()
    print('Generator Finished. Simulation over. Clearing dc_env...')


def init():
    increments = [4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]
    check_dir(OUTPUT_DIR)
    print("Registering the DC environment...")
    register_env("dc_env", get_env)

    print("Starting Ray...")
    ray.init(num_cpus=1, logging_level=logging.WARN)

    for tf_index, num_hosts in enumerate(increments):
        config = configure_ray(num_hosts, tf_index)
        print("Starting experiment.")
        tune_run(config)
        time.sleep(10)
        print("Experiment has completed.")
    time.sleep(10)
    plot_scalability_graph(increments, OUTPUT_DIR,
                           PLOT_DIR, "scalability_test")


if __name__ == '__main__':
    init()
