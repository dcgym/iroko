import time
import sys
import atexit
import numpy as np
from gym import Env as openAIGym, spaces
from dc_gym.control.iroko_bw_control import BandwidthController
from tqdm import tqdm

from iroko_traffic import TrafficGen
from iroko_state import StateManager
from factories import TopoFactory

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
    "agent": "TCP",
    # Which transport protocol to use. Defaults to the common TCP.
    "transport": "tcp",
    # How many steps to run the analysis for.
    "iterations": 10000,
    # Topology specific configuration (traffic pattern, number of hosts)
    "topo_conf": {"parallel_envs": False},
    # Specifies which variables represent the state of the environment:
    # Eligible variables:
    # "backlog", "olimit", "drops","bw_rx","bw_tx"
    # To measure the deltas between steps, prepend "d_" in front of a state.
    # For example: "d_backlog"
    "state_model": ["backlog"],
    # Add the flow matrix to state?
    "collect_flows": False,
    # Specifies which variables represent the state of the environment:
    # Eligible variables:
    # "action", "bw", "backlog","std_dev"
    "reward_model": ["backlog", "action"],
}


class DCEnv(openAIGym):
    WAIT = 0.05      # amount of seconds the agent waits per iteration
    ACTION_MIN = 0.01
    ACTION_MAX = 1.0
    __slots__ = ["conf", "topo", "traffic_gen", "state_man", "steps",
                 "reward", "progress_bar", "killed",
                 "input_file", "output_dir", "start_time"]

    def __init__(self, conf={}):
        self.conf = DEFAULT_CONF
        self.conf.update(conf)
        self.active = False
        # initialize the topology
        self.topo = self._create_topo(self.conf)

        # set the dimensions of the state matrix
        self._set_gym_spaces(self.conf)
        # Set the active traffic matrix
        self.input_file = None
        self.output_dir = None
        self.set_traffic_matrix(self.conf["tf_index"])

        # handle unexpected exits scenarios gracefully
        print("Registering signal handler.")
        # signal.signal(signal.SIGINT, self._handle_interrupt)
        # signal.signal(signal.SIGTERM, self._handle_interrupt)
        atexit.register(self.kill_env)

    def _start_env(self):
        self.topo.start_network()
        # initialize the traffic generator and state manager
        self.traffic_gen = TrafficGen(self.topo, self.conf["transport"])
        self.state_man = StateManager(self.topo, self.conf)
        self.bw_ctrl = BandwidthController(self.topo.host_ctrl_map)

        # set up variables for the progress bar
        self.steps = 0
        self.reward = 0
        self.progress_bar = tqdm(total=self.conf["iterations"], leave=False)
        self.progress_bar.clear()

        # Finally, initialize traffic
        self.start_traffic()
        self.start_time = time.time()
        self.active = True

    def reset(self):
        print("Stopping environment...")
        self.kill_env()
        print("Starting environment...")
        self._start_env()
        return np.zeros(self.observation_space.shape)

    def _create_topo(self, conf):
        conf["topo_conf"]["tcp_policy"] = conf["agent"].lower()
        # conf["topo_conf"]["parallel_envs"] = conf["parallel_envs"]
        return TopoFactory.create(conf["topo"], conf["topo_conf"])

    def _set_gym_spaces(self, conf):
        # set configuration for the gym environment
        num_ports = self.topo.get_num_sw_ports()
        num_actions = self.topo.get_num_hosts()
        num_features = len(self.conf["state_model"])
        if self.conf["collect_flows"]:
            num_features += num_actions * 2
        self.action_space = spaces.Box(
            low=self.ACTION_MIN, high=self.ACTION_MAX,
            dtype=np.float32, shape=(num_actions,))
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, dtype=np.int64,
            shape=(num_ports * num_features,))

    def set_traffic_matrix(self, index):
        traffic_file = self.topo.get_traffic_pattern(index)
        self.input_file = '%s/%s/%s' % (
            self.conf["input_dir"], self.conf["topo"], traffic_file)
        self.output_dir = '%s' % (self.conf["output_dir"])

    def step(self, action):
        self.steps = self.steps + 1
        self.progress_bar.set_postfix_str(s="%.3f reward" % self.reward)
        self.progress_bar.update(1)
        # if the traffic generator still going then the simulation is not over
        # let the agent predict bandwidth based on all previous information
        # perform actions
        done = not self.is_traffic_proc_alive()

        pred_bw = action * self.topo.conf["max_capacity"]
        # print("Iteration %d Actions: " % self.steps, end='')
        # for index, h_iface in enumerate(self.topo.host_ctrl_map):
        #     rate = action[index] * 10
        #     print(" %s:%.3f " % (h_iface, rate), end='')
        # print('')
        self.bw_ctrl.broadcast_bw(pred_bw, self.topo.host_ctrl_map)

        # observe for WAIT seconds minus time needed for computation
        max_sleep = max(self.WAIT - (time.time() - self.start_time), 0)
        time.sleep(max_sleep)
        self.start_time = time.time()
        do_sample = (self.steps % self.conf["sample_delta"]) == 0
        obs, self.reward = self.state_man.observe(pred_bw, do_sample)
        return obs.flatten(), self.reward, done, {}

    def render(self, mode='human'):
        raise NotImplementedError("Method render not implemented!")

    def _handle_interrupt(self, signum, frame):
        print("\nEnvironment: Caught interrupt")
        self.kill_env()
        sys.exit(1)

    def kill_env(self):
        # if not self.active:
        #     print("Chill, I am already cleaning up...")
        #     return
        # self.active = False
        if hasattr(self, 'progress_bar'):
            self.progress_bar.close()
        if hasattr(self, 'state_man'):
            print("Cleaning all state")
            self.state_man.terminate()
        if hasattr(self, 'traffic_gen'):
            print("Stopping traffic")
            self.traffic_gen.stop_traffic()
        if hasattr(self, 'topo'):
            print("Stopping network.")
            self.topo.stop_network()
        if hasattr(self, 'state_man'):
            print("Removing the state manager.")
            self.state_man.flush_and_close()
        print("Done with destroying myself.")

    def is_traffic_proc_alive(self):
        return self.traffic_gen.traffic_is_active()

    def start_traffic(self):
        self.traffic_gen.start_traffic(self.input_file, self.output_dir)
