import os
import datetime
import time
import socket

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
logging.basicConfig(format="%(levelname)s:%(message)s",
                    level=logging.INFO)
log = logging.getLogger(__name__)


# set up paths
exec_dir = os.getcwd()
file_dir = os.path.dirname(__file__)
INPUT_DIR = file_dir + '/inputs'
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
TUNE = True


def generate_testname(output_dir):
    n_folders = 0
    if os.path.isdir(output_dir):
        f_list = os.listdir(output_dir)
        n_folders = len(f_list)
    # Host name and a time stamp
    testname = "%s_%s" % (socket.gethostname(), n_folders)
    return testname


def dump_config(path, pattern):
    test_config = {}
    test_config["transport"] = TRANSPORT
    test_config["episodes"] = EPISODES
    test_config["runs"] = RUNS
    test_config["topology"] = TOPO
    test_config["tcp_algorithms"] = TCP_ALGOS
    test_config["rl_algorithms"] = RL_ALGOS
    test_config["rates"] = NETWORK_RATES
    test_config["pattern"] = pattern
    # Get a string formatted time stamp
    ts = time.time()
    st = datetime.datetime.fromtimestamp(ts).strftime('%Y_%m_%d_%H_%M_%S')
    test_config["timestamp"] = st
    dc_utils.dump_json(path=path, name="bench_config", data=test_config)


def launch_test(algo, results_subdir, transport, rate, pattern):
    # cmd = "sudo python3 run_ray.py "
    cmd = "-a %s " % algo
    cmd += "-e %d " % EPISODES
    cmd += "--output %s " % results_subdir
    cmd += "--topo %s " % TOPO
    if TUNE:
        cmd += "--tune "
    cmd += "--rate %d " % rate
    # always use TCP if we are dealing with a TCP algorithm
    cmd += "--transport %s " % transport
    cmd += "--pattern %d " % pattern
    log.info("Calling Ray command:")
    log.info("%s" % cmd)
    run_ray.main(cmd.split())


def run_tests(results_dir, pattern, rate):
    for index in range(RUNS):
        for transport in TRANSPORT:
            results_subdir = "%s/%s_run%d" % (results_dir,
                                              transport, index)
            for algo in RL_ALGOS:
                launch_test(algo, results_subdir, transport, rate, pattern)
        for algo in TCP_ALGOS:
            results_subdir = "%s/%s_run%d" % (results_dir, "tcp", index)
            launch_test(algo, results_subdir, "tcp", rate, pattern)


def init():
    for pattern in TF_PATTERNS:
        for rate in NETWORK_RATES:
            testname = generate_testname(OUTPUT_DIR)
            results_dir = "%s/%s" % (OUTPUT_DIR, testname)
            log.info("Saving results to %s" % results_dir)
            dc_utils.check_dir(results_dir)
            log.info("Dumping configuration in %s" % results_dir)
            dump_config(results_dir, pattern)
            run_tests(results_dir, pattern, rate)
            # Plot the results and save the graphs under the given test name
            plot(results_dir, PLOT_DIR, testname)


if __name__ == '__main__':
    # Start pre-defined tests
    init()
