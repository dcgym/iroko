import atexit
import numpy as np
import os
from multiprocessing import RawArray, RawValue
import ctypes
from gym import Env as openAIGym, spaces

import dc_gym.utils as dc_utils
from dc_gym.control.iroko_bw_control import BandwidthController
from dc_gym.iroko_sampler import StatsSampler
from dc_gym.iroko_traffic import TrafficGen
from dc_gym.iroko_state import StateManager
from dc_gym.utils import TopoFactory
from dc_gym.topos.network_manager import NetworkManager


import logging
log = logging.getLogger(__name__)
FILE_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_CONF = {
    # Input folder of the traffic matrix.
    "input_dir": f"{FILE_DIR}/inputs/",
    # Which traffic matrix to run. Defaults to the first item in the list.
    "tf_index": 0,
    # Output folder for the measurements during trial runs.
    "output_dir": "results/",
    # When to take state samples. Defaults to taking a sample at every step.
    "sample_delta": 1,
    # Use the simplest topology for tests.
    "topo": "dumbbell",
    # Which agent to use for traffic management. By default this is TCP.
    "agent": "tcp",
    # Which transport protocol to use. Defaults to the common TCP.
    "transport": "tcp",
    # If we have multiple environments, we need to assign unique ids
    "parallel_envs": False,
    # Topology specific configuration (traffic pattern, number of hosts)
    "topo_conf": {},
    # The network features supported by this environment
    "stats_dict": {"backlog": 0, "olimit": 1,
                   "drops": 2, "bw_rx": 3, "bw_tx": 4},
    # Specifies which variables represent the state of the environment:
    # Eligible variables are drawn from stats_dict
    # To measure the deltas between steps, prepend "d_" in front of a state.
    # For example: "d_backlog"
    "state_model": ["backlog", "d_backlog"],
    # Add the flow matrix to state?
    "collect_flows": False,
    # Specifies which variables represent the state of the environment:
    # Eligible variables:
    # "action", "queue","std_dev", "joint_queue", "fairness"
    "reward_model": ["joint_queue"],
}


def squash_action(action, action_min, action_max):
    action_diff = (action_max - action_min)
    return (np.tanh(action) + 1.0) / 2.0 * action_diff + action_min


def clip_action(action, action_min, action_max):
    """ Truncates the entries in action to the range defined between
    action_min and action_max. """
    return np.clip(action, action_min, action_max)


def sigmoid(action, derivative=False):
    sigm = 1. / (1. + np.exp(-action))
    if derivative:
        return sigm * (1. - sigm)
    return sigm


class DCEnv(openAIGym):
    __slots__ = ["conf", "topo", "traffic_gen", "state_man", "steps",
                 "terminated", "net_man", "input_file", "short_id",
                 "bw_ctrl", "sampler", "reward"]

    def __init__(self, conf={}):
        self.conf = DEFAULT_CONF
        self.conf.update(conf)

        # Init one-to-one mapped variables
        self.net_man = None
        self.state_man = None
        self.traffic_gen = None
        self.bw_ctrl = None
        self.sampler = None
        self.input_file = None
        self.terminated = False
        self.reward = RawValue('d', 0)
        self.steps = 0

        # set the id of this environment
        self.short_id = dc_utils.generate_id()
        if self.conf["parallel_envs"]:
            self.conf["topo_conf"]["id"] = self.short_id
        # initialize the topology
        self.topo = TopoFactory.create(self.conf["topo"],
                                       self.conf["topo_conf"])
        # Save the configuration we have, id does not matter here
        dc_utils.dump_json(path=self.conf["output_dir"],
                           name="env_config", data=self.conf)
        dc_utils.dump_json(path=self.conf["output_dir"],
                           name="topo_config", data=self.topo.conf)
        # set the dimensions of the state matrix
        self._set_gym_matrices(self.conf)
        # Set the active traffic matrix
        self._set_traffic_matrix(self.conf["tf_index"])

        # each unique id has its own sub folder
        if self.conf["parallel_envs"]:
            self.conf["output_dir"] += "/%s" % self.short_id
        # check if the directory we are going to work with exists
        dc_utils.check_dir(self.conf["output_dir"])

        # handle unexpected exits scenarios gracefully
        atexit.register(self.close)

    def _set_gym_matrices(self, conf):

        # set the action space
        num_actions = self.topo.get_num_hosts()
        min_bw = 10000.0 / float(self.topo.conf["max_capacity"])
        action_min = np.empty(num_actions)
        action_min.fill(min_bw)
        action_max = np.empty(num_actions)
        action_max.fill(1.0)
        self.action_space = spaces.Box(
            low=action_min, high=action_max, dtype=np.float64)
        # Initialize the action array shared with the control manager
        tx_rate = RawArray(ctypes.c_ulong, num_actions)
        self.tx_rate = dc_utils.shmem_to_nparray(tx_rate, np.int64)
        log.info("%s Setting action space" % (self.short_id))
        log.info(f"from {action_min}")
        log.info(f"to {action_max}")

        # set the observation space
        num_ports = self.topo.get_num_sw_ports()
        num_features = len(self.conf["state_model"])
        if self.conf["collect_flows"]:
            num_features += num_actions * 2
        obs_min = np.empty(num_actions)
        obs_min.fill(-np.inf)
        obs_max = np.empty(num_actions)
        obs_max.fill(np.inf)
        self.observation_space = spaces.Box(
            low=obs_min, high=obs_max, dtype=np.float64)

    def _set_traffic_matrix(self, index):
        traffic_file = self.topo.get_traffic_pattern(index)
        self.input_file = "%s/%s/%s" % (
            self.conf["input_dir"], self.conf["topo"], traffic_file)

    def _start_managers(self):
        # actually generate a topology if it does not exist yet
        if not self.net_man:
            log.info("%s Starting network manager..." % self.short_id)
            self.net_man = NetworkManager(self.topo,
                                          self.conf["agent"].lower())
        # in a similar way start a traffic generator
        if not self.traffic_gen:
            log.info("%s Starting traffic generator..." % self.short_id)
            self.traffic_gen = TrafficGen(self.net_man,
                                          self.conf["transport"],
                                          self.conf["output_dir"])
        # Init the state manager
        if not self.state_man:
            self.state_man = StateManager(self.conf,
                                          self.net_man,
                                          self.conf["stats_dict"])
        # Init the state sampler
        if not self.sampler:
            stats = self.state_man.get_stats()
            self.sampler = StatsSampler(stats, self.tx_rate,
                                        self.reward, self.conf["output_dir"])
            self.sampler.start()
        # the bandwidth controller is reinitialized with every new network
        if not self.bw_ctrl:
            host_map = self.net_man.host_ctrl_map
            self.bw_ctrl = BandwidthController(host_map, self.tx_rate)
            self.bw_ctrl.start()

    def _start_env(self):
        log.info("%s Starting environment..." % self.short_id)
        # reset the tracking statistics
        self.steps = 0
        self.reward = RawValue('f', 0)
        self.tx_rate.fill(self.topo.max_bps)
        # Launch all managers (if they are not active already)
        self._start_managers()
        # Finally, start the traffic
        self.traffic_gen.start(self.input_file)

    def _stop_env(self):
        log.info("%s Stopping environment..." % self.short_id)
        if self.traffic_gen:
            log.info("%s Stopping traffic" % self.short_id)
            self.traffic_gen.stop()
        log.info("%s Done with stopping." % self.short_id)

    def reset(self):
        self._stop_env()
        self._start_env()
        log.info("%s Done with resetting." % self.short_id)
        return np.zeros(self.observation_space.shape)

    def close(self):
        if self.terminated:
            return
        self.terminated = True
        log.info("%s Closing environment..." % self.short_id)
        if self.state_man:
            log.info("%s Stopping all state collectors..." % self.short_id)
            self.state_man.close()
            self.state_man = None
        if self.bw_ctrl:
            log.info("%s Shutting down bandwidth control..." % self.short_id)
            self.bw_ctrl.close()
            self.bw_ctrl = None
        if self.sampler:
            log.info("%s Shutting down data sampling." % self.short_id)
            self.sampler.close()
            self.sampler = None
        if self.traffic_gen:
            log.info("%s Shutting down generators..." % self.short_id)
            self.traffic_gen.close()
            self.traffic_gen = None
        if self.net_man:
            log.info("%s Stopping network." % self.short_id)
            self.net_man.stop_network()
            self.net_man = None
        log.info("%s Done with destroying myself." % self.short_id)

    def step(self, action):
        action = clip_action(action,
                             self.action_space.low,
                             self.action_space.high)
        obs, self.reward.value = self.state_man.observe(action)

        for index, a in enumerate(action):
            self.tx_rate[index] = a * self.topo.max_bps
        log.debug("%s Iteration %d" % (self.short_id, self.steps))
        log.debug("%s Reward: %.3f" % (self.short_id, self.reward.value))
        done = not self.traffic_gen.check_if_traffic_alive()
        self.steps = self.steps + 1
        return obs.flatten(), self.reward.value, done, {}

    def _handle_interrupt(self, signum, frame):
        log.warn("%s \nEnvironment: Caught interrupt" % self.short_id)
        atexit.unregister(self.close())
        self.close()
        exit(1)
