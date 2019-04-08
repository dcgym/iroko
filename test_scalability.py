from __future__ import print_function
from __future__ import division  # For Python 2
import numpy as np
import pandas as pd
from filelock import FileLock
import os
import logging
import time
import argparse
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
from matplotlib.ticker import FormatStrFormatter

PARSER = argparse.ArgumentParser()
PARSER.add_argument('--plot', '-p', action="store_true",
                    default=False, help='Only plot results.')
PARSER.add_argument('--input', '-i', dest='input_dir',
                    default="scalability_test")
ARGS = PARSER.parse_args()

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
TESTNAME = ARGS.input_dir
cwd = os.getcwd()
lib_dir = os.path.dirname(dc_gym.__file__)
INPUT_DIR = lib_dir + '/inputs'
OUTPUT_DIR = cwd + '/' + TESTNAME


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
        "topo_conf": {"num_hosts": num_hosts, "parallel_envs": True,
                      "max_capacity": 1000e9},
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


def plot_scalability_graph(increments, data_dirs, plot_dir, name):
    # Set seaborn style for plotting
    sns.set(style="whitegrid", rc={"lines.linewidth": 2.5})
    sns.set_context("paper")
    files = increments
    increments = [0] + increments
    agg_df = pd.DataFrame({'Number of Hosts': increments})
    for data_dir in data_dirs.keys():
        bw_list = {}
        bw_list["rx"] = []
        bw_list["tx"] = []
        for increment in files:
            stats_file = '%s/%s_hosts/runtime_statistics.npy' % (
                data_dir, increment)
            print("Loading %s..." % stats_file)
            try:
                with FileLock(stats_file + ".lock"):
                    statistics = np.load(stats_file).item()
            except Exception:
                print("Error loading file %s" % stats_file)
                continue
            port_stats = np.moveaxis(statistics["stats"], 0, -1)
            port_rx_bws = np.array(
                port_stats[STATS_DICT["bw_rx"]].mean(axis=1))
            port_tx_bws = np.array(
                port_stats[STATS_DICT["bw_tx"]].mean(axis=1))
            # bandwidths
            print("Computing mean of interface bandwidth per step.")
            bw_list["rx"].append(port_rx_bws.sum())
            bw_list["tx"].append(port_tx_bws.sum())
        bw_list["rx"] = [0] + bw_list["rx"]
        bw_list["tx"] = [0] + bw_list["tx"]
        agg_bw = np.add(bw_list["rx"], bw_list["tx"])
        t_df = pd.DataFrame({data_dirs[data_dir]: agg_bw})
        agg_df = pd.concat((agg_df, t_df), axis=1)
    agg_df.set_index('Number of Hosts', inplace=True)
    fig = sns.lineplot(data=agg_df, markers=True, markersize=8)
    fig.set_xscale('symlog', basex=2, linthreshx=4)
    fig.set_yscale('symlog', basey=2, linthreshy=4 * 10e6)
    fig.set(xlabel='Hosts', ylabel='Mbps (Avg)')
    y_increments = np.array(increments) * 10e6
    fig.set_yticks(y_increments)
    fig.set_yticklabels(increments)
    fig.set_xticks(increments)
    fig.set_xticklabels(increments)
    fig.set_ylim(ymin=0, ymax=y_increments[len(y_increments) - 1] + 100)
    fig.set_xlim(xmin=0, xmax=increments[len(increments) - 1] + 100)

    print("Test Summary:")
    print(agg_df)

    plt_name = "%s/" % (plot_dir)
    plt_name += "%s" % name
    print("Saving plot %s" % plt_name)
    check_plt_dir(plt_name)
    plt.savefig(plt_name + ".pdf", bbox_inches='tight', pad_inches=0.05)
    plt.savefig(plt_name + ".png", bbox_inches='tight', pad_inches=0.05)
    plt.gcf().clear()


def run(config):
    agent_class = get_agent(config["env_config"]["agent"])
    agent = agent_class(config=config, env="dc_env")
    agent.train()
    print('Generator Finished. Simulation over. Clearing dc_env...')


data_dirs = {
    "candidates/scalability_test_10mbit_60core": "60 Core Rate Limited",
    "candidates/scalability_test_gbit_60core": "60 Core Full",
    "candidates/scalability_test_10mbit_8core": "8 Core Rate Limited",
    "candidates/scalability_test_gbit_8core": "8 Core Full"}


def init():
    increments = [4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]
    if not ARGS.plot:
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
    plot_scalability_graph(increments, data_dirs,
                           PLOT_DIR, os.path.basename(TESTNAME.strip("/")))


if __name__ == '__main__':
    init()
