from __future__ import print_function
import sys
import atexit
import numpy as np
from multiprocessing import Array
from ctypes import c_ulong
from gym import Env as openAIGym, spaces

from dc_gym.control.iroko_bw_control import BandwidthController
from dc_gym.iroko_traffic import TrafficGen
from dc_gym.iroko_state import StateManager
from dc_gym.utils import TopoFactory
from dc_gym.topos.network_manager import NetworkManager
import dc_gym.utils as dc_utils

log = dc_utils.IrokoLogger.__call__().get_logger()

DEFAULT_CONF = {
    # Input folder of the traffic matrix.
    "input_dir": "../inputs/",
    # Which traffic matrix to run. Defaults to the first item in the list.
    "tf_index": 0,
    # Output folder for the measurements during trial runs.
    "output_dir": "../results/",
    # When to take state samples. Defaults to taking a sample at every step.
    "sample_delta": 1,
    # Basic environment name.
    "env": "iroko",
    # Use the simplest topology for tests.
    "topo": "dumbbell",
    # Which agent to use for traffic management. By default this is TCP.
    "agent": "tcp",
    # Which transport protocol to use. Defaults to the common TCP.
    "transport": "tcp",
    # How many steps to run the analysis for.
    "iterations": 10000,
    # Topology specific configuration (traffic pattern, number of hosts)
    "topo_conf": {},
    # Specifies which variables represent the state of the environment:
    # Eligible variables:
    # "backlog", "olimit", "drops","bw_rx","bw_tx"
    # To measure the deltas between steps, prepend "d_" in front of a state.
    # For example: "d_backlog"
    "state_model": ["backlog", "d_backlog"],
    # Add the flow matrix to state?
    "collect_flows": False,
    # Specifies which variables represent the state of the environment:
    # Eligible variables:
    # "action", "queue","std_dev", "joint_queue", "fairness"
    "reward_model": ["joint_queue"],
    # Are algorithms using their own squashing function or do we have to do it?
    "ext_squashing": True,
    "parallel_envs": False,
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
                 "reward", "pbar", "killed", "net_man", "input_file",
                 "short_id"]

    def __init__(self, conf={}):
        self.conf = DEFAULT_CONF
        self.conf.update(conf)

        # Init one-to-one mapped variables
        self.short_id = ""
        self.net_man = None
        self.traffic_gen = None
        self.bw_ctrl = None
        self.input_file = None

        # set the id of this environment
        if self.conf["parallel_envs"]:
            self.short_id = dc_utils.generate_id()
        # initialize the topology
        self.conf["topo_conf"]["id"] = self.short_id
        self.topo = TopoFactory.create(
            self.conf["topo"], self.conf["topo_conf"])
        # set the dimensions of the state matrix
        self._set_gym_matrices(self.conf)
        # Set the active traffic matrix
        self.set_traffic_matrix(self.conf["tf_index"])
        # Init the state manager
        self.state_man = StateManager(self.conf, self.topo)
        # handle unexpected exits scenarios gracefully
        log.info("Registering signal handler.")
        # signal.signal(signal.SIGINT, self._handle_interrupt)
        # signal.signal(signal.SIGTERM, self._handle_interrupt)
        atexit.register(self.close)

    def _set_gym_matrices(self, conf):
        # set configuration for the gym environment
        num_ports = self.topo.get_num_sw_ports()
        num_actions = self.topo.get_num_hosts()
        num_features = len(self.conf["state_model"])
        10e6 / self.topo.conf["max_capacity"]
        action_min = 10000.0 / float(self.topo.conf["max_capacity"])
        action_max = 1.0
        if self.conf["collect_flows"]:
            num_features += num_actions * 2
        self.action_space = spaces.Box(
            low=action_min, high=action_max,
            dtype=np.float64, shape=(num_actions,))
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, dtype=np.float64,
            shape=(num_ports * num_features,))
        log.info("Setting action space from %f to %f" %
                 (action_min, action_max))
        # Initialize the action array shared with the control manager
        tx_rate = Array(c_ulong, num_actions)
        self.tx_rate = dc_utils.shmem_to_nparray(tx_rate, np.int64)

    def set_traffic_matrix(self, index):
        traffic_file = self.topo.get_traffic_pattern(index)
        self.input_file = '%s/%s/%s' % (
            self.conf["input_dir"], self.conf["topo"], traffic_file)

        if self.short_id != "":
            self.conf["output_dir"] += "/%s" % self.short_id
            dc_utils.check_dir(self.conf["output_dir"])

    def _start_env(self):
        # start the manager with the live topology information
        self.traffic_gen = TrafficGen(self.net_man, self.conf["transport"])
        self.state_man.start(self.net_man)
        self.tx_rate.fill(self.topo.max_bps)
        self.bw_ctrl = BandwidthController(
            self.net_man.host_ctrl_map, self.tx_rate)
        self.steps = 0
        self.reward = 0

        # Finally, initialize traffic
        self.start_traffic()
        self.bw_ctrl.start()

    def _stop_env(self):
        log.info("Stopping environment...")
        if self.state_man:
            log.info("Stopping the state manager.")
            log.info("Cleaning all state.")
            self.state_man.terminate()
            self.state_man.flush_and_close()
        if self.bw_ctrl:
            log.info("Stopping bandwidth control.")
            self.bw_ctrl.terminate()
        if self.traffic_gen:
            log.info("Stopping traffic")
            self.traffic_gen.stop_traffic()
        log.info("Done with destroying myself.")

    def reset(self):
        # actually generate a topology if it does not exist yet
        if not self.net_man:
            log.info("Starting network manager...")
            self.net_man = NetworkManager(
                self.topo, self.conf["agent"].lower())
        self._stop_env()
        log.info("Starting environment...")
        self._start_env()
        return np.zeros(self.observation_space.shape)

    def step(self, action):
        do_sample = (self.steps % self.conf["sample_delta"]) == 0
        if not self.conf["ext_squashing"]:
            action = clip_action(
                action, self.action_space.low, self.action_space.high)
        obs, self.reward = self.state_man.observe(action, do_sample)

        for index, a in enumerate(action):
            self.tx_rate[index] = a * self.topo.max_bps

        # For now we run forever
        # done = not self.is_traffic_proc_alive()
        done = False

        # log.info("Iteration %d Actions: " % self.steps, end='')
        # for index, h_iface in enumerate(self.topo.host_ctrl_map):
        #     rate = action[index]
        #     log.info(" %s:%f " % (h_iface, rate), end='')
        # log.info('')
        # log.info("State:", obs)
        # log.info("Reward:", self.reward)
        # if self.steps & (32 - 1):
        # log.info(pred_bw)
        # if not self.steps & (64 - 1):
        #     self.bw_ctrl.broadcast_bw(pred_bw, self.topo.host_ctrl_map)
        self.steps = self.steps + 1
        return obs.flatten(), self.reward, done, {}

    def render(self, mode='human'):
        raise NotImplementedError("Method render not implemented!")

    def _handle_interrupt(self, signum, frame):
        log.info("\nEnvironment: Caught interrupt")
        self.close()
        sys.exit(1)

    def close(self):
        self._stop_env()
        if self.net_man:
            log.info("Stopping network.")
            self.net_man.stop_network()
        log.info("Done with destroying myself.")

    def is_traffic_proc_alive(self):
        return self.traffic_gen.traffic_is_active()

    def start_traffic(self):
        self.traffic_gen.start_traffic(self.input_file, self.conf["output_dir"]
                                       )
