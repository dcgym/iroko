from __future__ import print_function
import numpy as np


class RewardFunction:
    def __init__(self, host_ifaces, interfaces, reward_model,
                 max_queue, max_bw):
        self.interfaces = interfaces
        self.num_interfaces = len(interfaces)
        self.host_ifaces = host_ifaces
        self.reward_model = reward_model
        self.max_queue = max_queue
        self.max_bw = max_bw

    def get_reward(self, stats, actions):
        reward = 0
        if "action" in self.reward_model:
            action_reward = self._action_reward(actions)
            reward += action_reward
            print ("action: %f " % action_reward, end='')
        if "bw" in self.reward_model:
            bw_reward = self._bw_reward(stats[1])
            reward += bw_reward
            print ("bw: %f " % bw_reward, end='')
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
        for iface, iface_stats in stats.items():
            if iface in self.host_ifaces:
                bw_reward += iface_stats["bws_rx"] / float(self.max_bw)
        return bw_reward * weight

    def _queue_reward(self, stats):
        queue_reward = 0.0
        weight = 10 * float(self.num_interfaces) / float(len(self.host_ifaces))
        for iface, iface_stats in stats.items():
            queue_reward -= weight * \
                (float(iface_stats["queues"]) / float(self.max_queue))**2
        return queue_reward
