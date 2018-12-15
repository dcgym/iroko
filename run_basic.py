from __future__ import print_function
import argparse
import os

# Iroko imports
import dc_gym
from dc_gym.factories import EnvFactory

# set up paths
cwd = os.getcwd()
lib_dir = os.path.dirname(dc_gym.__file__)
INPUT_DIR = lib_dir + '/inputs'
OUTPUT_DIR = cwd + '/results'

PARSER = argparse.ArgumentParser()
PARSER.add_argument('--env', '-e', dest='env',
                    default='iroko', help='The platform to run.')
PARSER.add_argument('--topo', '-to', dest='topo',
                    default='dumbbell', help='The topology to operate on.')
PARSER.add_argument('--timesteps', '-t', dest='timesteps',
                    type=int, default=10000,
                    help='total number of timesteps to train rl agent')
PARSER.add_argument('--output', dest='output_dir', default=OUTPUT_DIR,
                    help='Folder which contains all the collected metrics.')
PARSER.add_argument('--transport', dest='transport', default="udp",
                    help='Choose the transport protocol of the hosts.')
ARGS = PARSER.parse_args()


def test_run(input_dir, output_dir, env, topo):
    # Assemble a configuration dictionary for the environment
    env_config = {
        "input_dir": input_dir,
        "output_dir": ARGS.output_dir,
        "env": ARGS.env,
        "topo": ARGS.topo,
        "agent": "RND",
        "transport": ARGS.transport,
        "tf_index": 0
    }
    dc_env = EnvFactory.create(env_config)
    for epoch in range(ARGS.timesteps):
        action = dc_env.action_space.sample()
        dc_env.step(action)
    print('Generator Finished. Simulation over. Clearing dc_env...')
    dc_env.kill_env()


def clean():
    print ("Removing all traces of Mininet")
    os.system('sudo mn -c')
    os.system("sudo killall -9 goben")
    os.system("sudo killall -9 node_control")


def init():
    test_run(INPUT_DIR, ARGS.output_dir, ARGS.env, ARGS.topo)


if __name__ == '__main__':
    init()
