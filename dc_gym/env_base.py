import numpy as np
import time
import signal
import sys
import atexit
from gym import Env as openAIGym, spaces
from tqdm import tqdm


from iroko_traffic import TrafficGen
from iroko_state import StateManager
from factories import TopoFactory


class BaseEnv(openAIGym):
    WAIT = 0.0      # amount of seconds the agent waits per iteration
    ACTION_MIN = 0.01
    ACTION_MAX = 1.0
    __slots__ = ["conf", "topo", "traffic_gen", "state_man", "num_ports",
                 "num_features", "num_actions", "steps", "reward",
                 "progress_bar", "_handle_interrupt", "kill_env", "killed",
                 "input_file", "output_dir"]

    def __init__(self, conf):
        self.conf = conf
        # initialize the topology
        self.topo = self._create_topo(conf)
        # initialize the traffic generator and state manager
        self.traffic_gen = TrafficGen(self.topo, conf["transport"])
        self.state_man = StateManager(self.topo, conf)

        # set configuration for the gym environment
        self.num_ports = len(self.topo.get_sw_ports())
        self.num_features = self.state_man.num_features
        self.num_actions = len(self.topo.host_ctrl_map)
        self.action_space = spaces.Box(
            low=self.ACTION_MIN, high=self.ACTION_MAX, dtype=np.float32,
            shape=(self.num_actions, ))
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, dtype=np.float32,
            shape=(self.num_ports * self.num_features, ))

        # set up variables for the progress bar
        self.steps = 0
        self.reward = 0
        # self.progress_bar = tqdm(total=self.conf["iterations"], leave=False)
        # self.progress_bar.clear()
        # handle unexpected exits scenarios gracefully
        print("Registering signal handler.")
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)
        atexit.register(self.kill_env)
        self.killed = False

        # Finally, initialize traffic
        self.input_file = None
        self.output_dir = None
        self.set_traffic_matrix(conf["tf_index"])
        self.start_traffic()

    def _create_topo(self, conf):
        topo_options = []
        if "parallel_envs" in conf.keys():
            topo_options.append("parallel_envs")
        topo_options.append(conf["agent"].lower())
        return TopoFactory.create(conf["topo"], topo_options)

    def set_traffic_matrix(self, index):
        traffic_files = self.topo.TRAFFIC_FILES
        traffic_file = traffic_files[index]
        self.input_file = '%s/%s/%s' % (
            self.conf["input_dir"], self.conf["topo"], traffic_file)
        self.output_dir = '%s/%s' % (self.conf["output_dir"], traffic_file)

    def step(self, action):
        self.steps = self.steps + 1
        # self.progress_bar.set_postfix_str(s="%.3f reward" % self.reward)
        # self.progress_bar.update(1)

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
        print ("\nEnvironment: Caught interrupt")
        self.kill_env()
        sys.exit(1)

    def kill_env(self):
        if (self.killed):
            print("Chill, I am already cleaning up...")
            return
        self.killed = True
        # self.progress_bar.close()
        self.state_man.terminate()
        self.traffic_gen.stop_traffic()
        self.topo.delete_topo()
        print ("Done with destroying myself.")

    def get_topo(self):
        return self.topo

    def is_traffic_proc_alive(self):
        return self.traffic_gen.traffic_is_active()

    def start_traffic(self):
        self.traffic_gen.start_traffic(self.input_file, self.output_dir)
