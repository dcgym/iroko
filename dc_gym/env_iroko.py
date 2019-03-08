from __future__ import print_function
import time
from dc_gym.env_base import BaseEnv
from dc_gym.control.iroko_bw_control import BandwidthController


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
    # Multiple environments require random interface ids.
    "parallel_envs": False,
}


def merge_dicts(x, y):
    """Given two dicts, merge them into a new dict as a shallow copy."""
    z = x.copy()
    z.update(y)
    return z


class DCEnv(BaseEnv):
    WAIT = 0.1      # amount of seconds the agent waits per iteration
    __slots__ = ["bw_ctrl"]

    def __init__(self, conf={}):
        conf = merge_dicts(DEFAULT_CONF, conf)
        BaseEnv.__init__(self, conf)
        self.bw_ctrl = BandwidthController(self.topo.host_ctrl_map)

    def step(self, action):
        BaseEnv.step(self, action)
        # if the traffic generator still going then the simulation is not over
        # let the agent predict bandwidth based on all previous information
        # perform actions
        done = not self.is_traffic_proc_alive()

        pred_bw = action * self.topo.MAX_CAPACITY
        print("Iteration %d Actions: " % self.steps, end='')
        for index, h_iface in enumerate(self.topo.host_ctrl_map):
            rate = action[index] * 10
            print(" %s:%.3f " % (h_iface, rate), end='')
        print('')
        self.bw_ctrl.broadcast_bw(pred_bw, self.topo.host_ctrl_map)

        # observe for WAIT seconds minus time needed for computation
        max_sleep = max(self.WAIT - (time.time() - self.start_time), 0)
        time.sleep(max_sleep)
        self.start_time = time.time()
        do_sample = (self.steps % self.conf["sample_delta"]) == 0
        obs, self.reward = self.state_man.observe(pred_bw, do_sample)
        return obs.flatten(), self.reward, done, {}
