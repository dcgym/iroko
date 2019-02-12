from __future__ import print_function
import numpy as np


class RewardFunction:
    def __init__(self, host_ifaces, interfaces, reward_model,
                 max_queue, max_bw, q_dict):
        self.interfaces = interfaces
        self.num_interfaces = len(interfaces)
        self.host_ifaces = host_ifaces
        self.reward_model = reward_model
        self.max_queue = max_queue
        self.max_bw = max_bw
        self.q_dict = q_dict

    def get_reward(self, stats, actions):
        reward = 0
        if "action" in self.reward_model:
            action_reward = self._action_reward(actions)
            print ("action pure: %f " % action_reward, end='')
            print ("action adj: %f " % action_reward, end='')
            action_reward = self._adjust_reward(action_reward, stats[2])
            reward += action_reward
        if "bw" in self.reward_model:
            bw_reward = self._bw_reward(stats[1])
            print ("bw pure: %f " % bw_reward, end='')
            bw_reward = self._adjust_reward(bw_reward, stats[2])
            print ("bw adjusted: %f " % bw_reward, end='')
            reward += bw_reward
        if "queue" in self.reward_model:
            queue_reward = self._queue_reward(stats[0])
            reward += queue_reward
            print ("queue: %f " % queue_reward, end='')
        if "std_dev" in self.reward_model:
            std_dev_reward = self._std_dev_reward(actions)
            reward += std_dev_reward
            print ("std_dev: %f " % std_dev_reward, end='')
        print("Total: %f" % reward)
        return reward

    def _adjust_reward(self, reward, queue_deltas):
        if "d_ol" in self.reward_model:
            tmp_list = []
            for d in queue_deltas.values():
                tmp_list.append(d["delta_overlimits"])
            if np.mean(tmp_list) > 0:
                reward /= 2
        if "d_drops" in self.reward_model:
            tmp_list = []
            for d in queue_deltas.values():
                tmp_list.append(d["delta_drops"])
                d["delta_drops"]
            if np.mean(tmp_list) > 0:
                reward /= 2
        return reward

    def _std_dev_reward(self, actions):
        pb_bws = list(actions.values())
        return -(np.std(pb_bws) / float(self.max_bw))

    def _action_reward(self, actions):
        action_reward = 0.0
        weight = float(len(self.host_ifaces)) / float(self.num_interfaces)
        for bw in actions.values():
            action_reward += bw / float(self.max_bw)
        return action_reward * weight

    def _bw_reward(self, stats):
        bw_reward = 0.0
        weight = float(len(self.host_ifaces)) / float(self.num_interfaces)
        for index, iface in enumerate(self.interfaces):
            if iface in self.host_ifaces:
                offset = len(self.bw_dict) * index
                bw = stats[offset + self.bw_dict["bw_rx"]]
                bw_reward += bw / float(self.max_bw)
        return bw_reward * weight

    def _queue_reward(self, stats):
        queue_reward = 0.0
        weight = float(self.num_interfaces) / float(len(self.host_ifaces))
        for index, iface in enumerate(self.interfaces):
            offset = len(self.q_dict) * index
            queue = stats[offset + self.q_dict["backlog"]]
            queue_reward -= weight * (float(queue) / float(self.max_queue))**2
        return queue_reward
