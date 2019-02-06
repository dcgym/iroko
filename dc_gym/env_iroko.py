from __future__ import print_function
import time
from env_base import BaseEnv
from control.iroko_bw_control import BandwidthController


class DCEnv(BaseEnv):

    def __init__(self, conf):
        # inputs:
        # reward_fun: a string  or function which calculates the reward
        BaseEnv.__init__(self, conf)
        self.ic = BandwidthController("Iroko", self.topo_conf.host_ctrl_map)
        self.start_time = time.time()

    def step(self, action):
        BaseEnv.step(self, action)
        # if the traffic generator still going then the simulation is not over
        # let the agent predict bandwidth based on all previous information
        # perform actions
        done = not self.is_traffic_proc_alive()

        pred_bw = {}
        # print ("Actions: ", end='')
        for i, h_iface in enumerate(self.topo_conf.host_ctrl_map):
            pred_bw[h_iface] = action[i] * self.topo_conf.MAX_CAPACITY
            # rate = h_iface, pred_bw[h_iface] * 10 / self.topo_conf.MAX_CAPACITY
            # print("%s:%.2fmb " % (rate), end='')
        self.ic.broadcast_bw(pred_bw)

        # observe for WAIT seconds minus time needed for computation
        max_sleep = max(self.WAIT - (time.time() - self.start_time), 0)
        time.sleep(max_sleep)
        self.start_time = time.time()
        # print ("")

        obs = self.state_man.collect()
        reward = self.state_man.compute_reward(pred_bw)
        ret = obs.reshape(self.num_ports * self.num_features), reward, done, {}
        return ret
