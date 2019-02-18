from __future__ import print_function
import time
from dc_gym.env_base import BaseEnv
from dc_gym.control.iroko_bw_control import BandwidthController


class DCEnv(BaseEnv):
    WAIT = 0.0      # amount of seconds the agent waits per iteration
    __slots__ = ["bw_ctrl"]

    def __init__(self, conf):
        BaseEnv.__init__(self, conf)
        self.bw_ctrl = BandwidthController(self.topo.host_ctrl_map)

    def step(self, action):
        BaseEnv.step(self, action)
        # if the traffic generator still going then the simulation is not over
        # let the agent predict bandwidth based on all previous information
        # perform actions
        done = not self.is_traffic_proc_alive()

        pred_bw = action * self.topo.MAX_CAPACITY
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

        obs = self.state_man.observe()
        self.reward = self.state_man.compute_reward(pred_bw)
        return obs.flatten(), self.reward, done, {}
