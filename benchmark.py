import os
import datetime
import time
import socket
import argparse

import run_ray
from plot import plot

import dc_gym.utils as dc_utils

import logging
# Fix a bug introduced by an annoying Google extension
import absl.logging
try:
    logging.root.removeHandler(absl.logging._absl_handler)
    absl.logging._warn_preinit_stderr = False
except Exception as e:
    print("Failed to fix absl logging bug", e)
# configure logging
logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# set up paths
exec_dir = os.getcwd()
file_dir = os.path.dirname(__file__)
OUTPUT_DIR = exec_dir + '/results'
PLOT_DIR = exec_dir + '/plots'

# RL Algorithms: PPO, APPO, DDPG, TD3, PG, A2C, RND
# TCP Algorithms: TCP, DCTCP, TCP_NV, PCC
RL_ALGOS = ["APPO", "TD3", "A2C"]
TCP_ALGOS = ["DCTCP", "TCP_NV"]
ALGOS = RL_ALGOS + TCP_ALGOS
# Transport Protocols: tcp, udp
TRANSPORT = ["udp", "tcp"]
TF_PATTERNS = [0]
RUNS = 1
EPISODES = 60
TOPO = "dumbbell"
NETWORK_RATES = [10, 1000]
TUNE = False


def generate_testname(output_dir):
    n_folders = 0
    if os.path.isdir(output_dir):
        f_list = os.listdir(output_dir)
        n_folders = len(f_list)
    # Host name and a time stamp
    testname = "%s_%s" % (socket.gethostname(), n_folders)
    return testname


def dump_config(args, path, pattern):
    test_config = {}
    test_config["transport"] = args.transports
    test_config["episodes"] = args.episodes
    test_config["runs"] = args.runs
    test_config["topology"] = args.topo
    test_config["tcp_algorithms"] = args.tcp_algos
    test_config["rl_algorithms"] = args.rl_algos
    test_config["rates"] = args.network_rates
    test_config["pattern"] = pattern
    # Get a string formatted time stamp
    ts = time.time()
    st = datetime.datetime.fromtimestamp(ts).strftime('%Y_%m_%d_%H_%M_%S')
    test_config["timestamp"] = st
    dc_utils.dump_json(path=path, name="bench_config", data=test_config)


def launch_test(algo, results_subdir, transport, rate, topo,  pattern, episodes):
    cmd = "-a %s " % algo
    cmd += "-e %d " % episodes
    cmd += "--output %s " % results_subdir
    cmd += "--topo %s " % topo
    if TUNE:
        cmd += "--tune "
    cmd += "--rate %d " % rate
    # always use TCP if we are dealing with a TCP algorithm
    cmd += "--transport %s " % transport
    cmd += "--pattern %d " % pattern
    log.info("Calling Ray command:")
    log.info("%s", cmd)
    run_ray.main(cmd.split())


def run_tests(args, results_dir, pattern, rate):
    for index in range(args.runs):
        for transport in args.transports:
            results_subdir = "%s/%s_run%d" % (results_dir, transport, index)
            for algo in args.rl_algos:
                launch_test(algo, results_subdir, transport, rate,
                            args.topo, pattern, args.episodes)
        for algo in args.tcp_algos:
            results_subdir = "%s/%s_run%d" % (results_dir, "tcp", index)
            launch_test(algo, results_subdir, "tcp", rate,
                        args.topo, pattern, args.episodes)


def get_args():
    p = argparse.ArgumentParser()
    p.add_argument('--rl_algos',
                   dest='rl_algos',
                   type=list,
                   nargs='+',
                   default=RL_ALGOS,
                   help='The reinforcement learning algorithms to test.')
    p.add_argument('--tcp_algos',
                   dest='tcp_algos',
                   type=list,
                   nargs='+',
                   default=TCP_ALGOS,
                   help='The TCP algorithms to test.')
    p.add_argument('--transports',
                   dest='transports',
                   type=list,
                   nargs='+',
                   default=TRANSPORT,
                   help='The transport protocol choices to test.')
    p.add_argument('--traffic_patterns',
                   dest='tf_patterns',
                   type=list,
                   nargs='+',
                   default=TF_PATTERNS,
                   help='The list of traffic patterns to use')
    p.add_argument('--network_rates',
                   dest='network_rates',
                   type=list,
                   nargs='+',
                   default=NETWORK_RATES,
                   help='The link bandwidths of the network (Mbps) to test.')
    p.add_argument('--topo',
                   '-t',
                   dest='topo',
                   type=str.lower,
                   default=TOPO,
                   help='The topology to operate on.')
    p.add_argument('--episodes',
                   '-e',
                   dest='episodes',
                   type=int,
                   default=EPISODES,
                   help='Total number of episodes to train the RL agent.')
    p.add_argument('--runs',
                   '-r',
                   dest='runs',
                   type=int,
                   default=RUNS,
                   help='Total number of repeated runs of this configuration.')
    p.add_argument('--output_dir',
                   dest='output_dir',
                   default=OUTPUT_DIR,
                   help='Folder which contains all the collected metrics.')
    p.add_argument('--plot_dir',
                   dest='plot_dir',
                   default=PLOT_DIR,
                   help='Folder where the plots will be saved.')
    p.add_argument('--tune',
                   action="store_true",
                   default=False,
                   help='Specify whether to run the tune framework')
    return p.parse_args()


def init(args):
    for pattern in args.tf_patterns:
        for rate in args.network_rates:
            testname = generate_testname(args.output_dir)
            results_dir = "%s/%s" % (args.output_dir, testname)
            log.info("Saving results to %s", results_dir)
            dc_utils.check_dir(results_dir)
            log.info("Dumping configuration in %s", results_dir)
            dump_config(args, results_dir, pattern)
            run_tests(args, results_dir, pattern, rate)
            # Plot the results and save the graphs under the given test name
            plot(results_dir, args.plot_dir, testname)


if __name__ == '__main__':
    args = get_args()
    # Start pre-defined tests
    init(args)
