import numpy as np
from gym import Env as openAIGym, spaces
import time
import signal
import sys
import atexit

from iroko_traffic import TrafficGen
from iroko_state import StateManager
from factories import TopoFactory


class BaseEnv(openAIGym):
    WAIT = 0.0      # amount of seconds the agent waits per iteration
    COLOR = 'blue'  # Color of the
    ALGO = 'base'   # Name of the environment
    ACTION_MIN = 0.1
    ACTION_MAX = 1.0

    def __init__(self, conf):
        self.conf = conf
        self.topo_conf = self._create_topo(conf)
        self.ports = self.topo_conf.get_sw_ports()
        self.num_ports = len(self.ports)
        self.traffic_gen = TrafficGen(self.topo_conf, conf["transport"])
        self.state_man = StateManager(self.topo_conf, conf)

        self.num_features = self.state_man.num_features
        self.num_actions = len(self.topo_conf.host_ctrl_map)
        self.action_space = spaces.Box(
            low=self.ACTION_MIN, high=self.ACTION_MAX, dtype=np.float32,
            shape=(self.num_actions, ))
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, dtype=np.float32,
            shape=(self.num_ports * self.num_features, ))

        # handle unexpected exits scenarios gracefully
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)
        atexit.register(self.kill_env)
        self.killed = False

        # Finally, initialize traffic
        self.set_traffic_matrix(conf["tf_index"])
        self.start_traffic()

    def _create_topo(self, conf):
        topo_options = {}
        topo_options["topo_name"] = conf["topo"]
        topo_options["enable_ecn"] = False
        if conf["agent"] == "DCTCP":
            topo_options["is_dctcp"] = True
        if conf["agent"] == "TCP_NV":
            topo_options["is_nv"] = True
        return TopoFactory.create(topo_options)

    def set_traffic_matrix(self, index):
        self.traffic_files = self.topo_conf.TRAFFIC_FILES
        self.traffic_file = self.traffic_files[index]
        self.input_file = '%s/%s/%s' % (
            self.conf["input_dir"], self.conf["topo"], self.traffic_file)
        self.output_dir = '%s/%s' % (self.conf["output_dir"],
                                     self.traffic_file)

    def step(self, action):
        raise NotImplementedError("Method step not implemented!")

    def reset(self):
        print ("Resetting environment...")
        if self.is_traffic_proc_alive():
            self.state_man.reset()
            self.traffic_gen.stop_traffic()

            self.traffic_gen.start_traffic(self.input_file, self.output_dir)
            self.start_time = time.time()
        return np.zeros(self.num_ports * self.num_features)

    def render(self, mode='human', close=False):
        raise NotImplementedError("Method render not implemented!")

    def _handle_interrupt(self, signum, frame):
        print ("\nCaught interrupt")
        self.kill_env()
        sys.exit(1)

    def kill_env(self):
        if (self.killed):
            print("Chill, I am already cleaning up...")
            return
        self.killed = True
        self.state_man.terminate()
        self.traffic_gen.stop_traffic()
        net = self.topo_conf.get_net()
        if (net is not None):
            net.stop()
        print ("Done with destroying myself.")

    def get_topo_conf(self):
        return self.topo_conf

    def is_traffic_proc_alive(self):
        return self.traffic_gen.traffic_is_active()

    def start_traffic(self):
        self.traffic_gen.start_traffic(self.input_file, self.output_dir)
