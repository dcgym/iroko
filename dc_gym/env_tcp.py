from __future__ import print_function
import time

from env_base import BaseEnv


class DCEnv(BaseEnv):
    COLOR = 'yellow'
    ALGO = 'tcp'

    def __init__(self, conf):
        BaseEnv.__init__(self, conf)
        self.start_time = time.time()

    def step(self, action):
        # if the trafic generator still going then the simulation is not over
        # let the agent predict bandwidth based on all previous information
        # perform actions
        done = not self.is_traffic_proc_alive()

        pred_bw = {}
        print ("Actions: ", end='')
        for i, h_iface in enumerate(self.topo_conf.host_ctrl_map):
            pred_bw[h_iface] = int(self.topo_conf.MAX_CAPACITY)
            print("%s:%.2fmb " % (
                h_iface,
                pred_bw[h_iface] * 10 / self.topo_conf.MAX_CAPACITY), end='')
        # observe for WAIT seconds minus time needed for computation
        time.sleep(max(round(self.WAIT - (time.time() - self.start_time), 3), 0))
        self.start_time = time.time()
        print ("")

        obs = self.state_man.collect()
        reward = self.state_man.compute_reward(pred_bw)
        if (done):
            self.state_man.save()
        return obs.reshape(self.num_ports * self.num_features), reward, done, {}
