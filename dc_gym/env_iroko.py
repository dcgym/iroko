from __future__ import print_function
import time
from dc_gym.env_base import BaseEnv, merge_dicts
from dc_gym.control.iroko_bw_control import BandwidthController


DEFAULT_CONF = {}


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

        pred_bw = action * self.topo.conf["max_capacity"]
        # print("Iteration %d Actions: " % self.steps, end='')
        # for index, h_iface in enumerate(self.topo.host_ctrl_map):
        #     rate = action[index] * 10
        #     print(" %s:%.3f " % (h_iface, rate), end='')
        # print('')
        # self.bw_ctrl.broadcast_bw(pred_bw, self.topo.host_ctrl_map)

        # observe for WAIT seconds minus time needed for computation
        max_sleep = max(self.WAIT - (time.time() - self.start_time), 0)
        time.sleep(max_sleep)
        self.start_time = time.time()
        do_sample = (self.steps % self.conf["sample_delta"]) == 0
        obs, self.reward = self.state_man.observe(pred_bw, do_sample)
        return obs.flatten(), self.reward, done, {}
