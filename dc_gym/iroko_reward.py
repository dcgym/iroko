from __future__ import print_function
import numpy as np


class RewardFunction:
    def __init__(self, host_ports, sw_ports, reward_model,
                 max_queue, max_bw, stats_dict):
        self.sw_ports = sw_ports
        self.num_sw_ports = len(sw_ports)
        self.host_ports = host_ports
        self.reward_model = reward_model
        self.max_queue = max_queue
        self.max_bw = max_bw
        self.stats_dict = stats_dict

    def get_reward(self, stats, deltas, actions):
        reward = 0
        if "action" in self.reward_model:
            action_reward = self._action_reward(actions)
            # print("action: %f " % action_reward, end='')
            reward += action_reward
        if "bw" in self.reward_model:
            bw_reward = self._bw_reward(stats)
            # print("bw: %f " % bw_reward, end='')
            bw_reward = self._adjust_reward(bw_reward, deltas)
            reward += bw_reward
        if "backlog" in self.reward_model:
            queue_reward = self._queue_reward(stats)
            reward += queue_reward
            # print("queue: %f " % queue_reward, end='')
        if "joint_backlog" in self.reward_model:
            joint_queue_reward = self._joint_queue_reward(actions, stats)
            reward += joint_queue_reward
            # print("joint queue: %f " % joint_queue_reward, end='')
        if "std_dev" in self.reward_model:
            std_dev_reward = self._std_dev_reward(actions)
            reward += std_dev_reward
            # print("std_dev: %f " % std_dev_reward, end='')
        if "fairness" in self.reward_model:
            fairness_reward = self.fairness(actions)
            reward += fairness_reward
            # print("fairness: %f " % fairness_reward, end='')
        # print("Total: %f" % reward)
        return reward

    def _adjust_reward(self, reward, queue_deltas):
        if "olimit" in self.reward_model:
            tmp_list = []
            for port_stats in queue_deltas:
                tmp_list.append(port_stats[self.stats_dict["olimit"]])
            if any(tmp_list):
                reward /= 4
        if "drops" in self.reward_model:
            tmp_list = []
            for port_stats in queue_deltas:
                tmp_list.append(port_stats[self.stats_dict["drops"]])
            if any(tmp_list):
                reward /= 4
        return reward

    def _std_dev_reward(self, actions):
        return -(np.std(actions) / float(self.max_bw))

    def _fairness_reward(self, actions):
        '''Compute Jain's fairness index for a list of values.
        See http://en.wikipedia.org/wiki/Fairness_measure for fairness equations.
        @param values: list of values
        @return fairness: JFI
        '''
        num = sum(actions) ** 2
        denom = len(actions) * sum([i ** 2 for i in actions])
        return num / float(denom)

    def _action_reward(self, actions):
        action_reward = []
        for bw in actions:
            action_reward.append(bw / float(self.max_bw))
        return np.average(action_reward)

    def _bw_reward(self, stats):
        bw_reward = []
        for index, iface in enumerate(self.sw_ports):
            if iface in self.host_ports:
                bw = stats[self.stats_dict["bw_rx"]][index]
                bw_reward.append(bw / float(self.max_bw))
        return np.average(bw_reward)

    def _queue_reward(self, stats):
        queue_reward = 0.0
        weight = float(self.num_sw_ports) / float(len(self.host_ports))
        for index, _ in enumerate(self.sw_ports):
            queue = stats[self.stats_dict["backlog"]][index]
            queue_reward -= (float(queue) / float(self.max_queue))**2
        return queue_reward * weight

    def _joint_queue_reward(self, actions, stats):
        queue_reward = 0.0
        weight = float(self.num_sw_ports) / float(len(self.host_ports))
        add_action_reward = True
        for index, _ in enumerate(self.sw_ports):
            queue = stats[self.stats_dict["backlog"]][index]
            queue_percent = (float(queue) / float(self.max_queue))
            queue_reward -= queue_percent
            if queue_percent > 0.10:
                add_action_reward = False
        joint_reward = queue_reward * weight
        if add_action_reward:
            joint_reward += self._action_reward(actions)
        return joint_reward
