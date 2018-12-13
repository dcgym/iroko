from __future__ import print_function
import os
import subprocess
import datetime
import time
import json
import socket
from plot import plot


# set up paths
exec_dir = os.getcwd()
file_dir = os.path.dirname(__file__)
INPUT_DIR = file_dir + '/inputs'
OUTPUT_DIR = exec_dir + '/results'
PLOT_DIR = exec_dir + '/plots'
RL_ALGOS = ["PPO", "DDPG", "PG"]
TCP_ALGOS = ["TCP", "DCTCP", "TCP_NV"]
ALGOS = RL_ALGOS + TCP_ALGOS
TRANSPORT = ["udp", "tcp"]
RUNS = 5
STEPS = 200000
TOPO = "dumbbell"
TUNE = False
RESTORE = False
RESTORE_PATH = file_dir + "./"


def check_dir(directory):
    # create the folder if it does not exit
    if not directory == '' and not os.path.exists(directory):
        print("Folder %s does not exist! Creating..." % directory)
        os.makedirs(directory)


def generate_testname(output_dir):
    n_folders = 0
    if os.path.isdir(output_dir):
        list = os.listdir(output_dir)
        n_folders = len(list)
    # Host name and a time stamp
    testname = "%s_%s" % (socket.gethostname(), n_folders)
    return testname


def dump_config(path, transport):
    test_config = {}
    test_config["transport"] = transport
    test_config["timesteps"] = STEPS
    test_config["runs"] = RUNS
    test_config["topology"] = TOPO
    test_config["algorithms"] = ALGOS
    # Get a string formatted time stamp
    ts = time.time()
    st = datetime.datetime.fromtimestamp(ts).strftime('%Y_%m_%d_%H_%M_%S')
    test_config["timestamp"] = st
    with open(path + "/test_config.json", 'w') as fp:
        json.dump(test_config, fp)


def run_tests():
    for transport in TRANSPORT:
        testname = generate_testname(OUTPUT_DIR)
        results_dir = "%s/%s" % (OUTPUT_DIR, testname)
        print ("Saving results to %s" % results_dir)
        check_dir(results_dir)
        print ("Dumping configuration in %s" % results_dir)
        dump_config(results_dir, transport)
        for index in range(RUNS):
            results_subdir = "%s/run%d" % (results_dir, index)
            for algo in ALGOS:
                cmd = "sudo python run_ray.py "
                cmd += "-a %s " % algo
                cmd += "-t %d " % STEPS
                cmd += "--output %s " % results_subdir
                cmd += "--topo %s " % TOPO
                if (TUNE):
                    cmd += "--tune "
                if (RESTORE):
                    cmd += "--restore %s " % RESTORE_PATH
                if (algo in TCP_ALGOS):
                    cmd += " --env tcp --transport tcp"
                else:
                    cmd += "--transport %s" % transport
                subprocess.call(cmd.split())
        # Plot the results and save the graphs under the given test name
        plot(results_dir, PLOT_DIR, testname)


if __name__ == '__main__':
    # Start pre-defined tests
    run_tests()
