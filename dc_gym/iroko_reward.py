from __future__ import print_function
import numpy as np
import math
from dc_gym.log import IrokoLogger
log = IrokoLogger("iroko")


def std_dev_reward(actions):
    return -np.std(actions)


def fairness_reward(actions):
    '''Compute Jain's fairness index for a list of values.
    See http://en.wikipedia.org/wiki/Fairness_measure for fairness equations.
    @param values: list of values
    @return fairness: JFI
    '''
    num = sum(actions) ** 2
    denom = len(actions) * sum([i ** 2 for i in actions])
    return num / float(denom)


def bw_reward(bws, host_ports, sw_ports):
    bw_reward = []
    for index, iface in enumerate(sw_ports):
        if iface in host_ports:
            bw_reward.append(bws[index])
    return np.mean(bw_reward)


def action_reward(actions):
    return np.mean(actions)


def joint_queue_reward(actions, queues):
    queue = np.max(queues)
    action = np.mean(actions)
    reward = action - 2 * (action * queue)
    return reward


def queue_reward(queues):
    queue_reward = -np.sum(queues)**2
    return queue_reward


def selu(x):
    alpha = 1.6732632423543772848170429916717
    scale = 1.0507009873554804934193349852946
    reward = scale * (max(0, x) + min(0, alpha * (math.exp(x) - 1)))
    return reward


def step_reward(actions, queues):
    queue = np.max(queues)
    action = np.mean(actions)
    if queue > 0.50:
        return (1 - action)
    else:
        return action + (1 - queue)


class RewardFunction:
    def __init__(self, topo_conf, reward_model, stats_dict):
        self.sw_ports = topo_conf.get_sw_ports()
        self.host_ports = topo_conf.get_host_ports()
        self.max_queue = topo_conf.max_queue
        self.max_bps = topo_conf.max_bps
        self.num_sw_ports = topo_conf.get_num_sw_ports()
        self.reward_model = reward_model
        self.stats_dict = stats_dict

    def get_reward(self, stats, deltas, actions):
        reward = 0
        if "action" in self.reward_model:
            actions = action_reward(actions)
            # log.info("action: %f " % tmp_reward, end='')
            reward += actions
        if "bw" in self.reward_model:
            bws = stats[self.stats_dict["bw_rx"]]
            tmp_reward = bw_reward(bws, self.host_ports, self.sw_ports)
            # log.info("bw: %f " % tmp_reward, end='')
            reward += tmp_reward
        if "backlog" in self.reward_model:
            queues = stats[self.stats_dict["backlog"]]
            tmp_reward = queue_reward(queues)
            reward += tmp_reward
            # log.info("queue: %f " % tmp_reward, end='')
        if "joint_backlog" in self.reward_model:
            queues = stats[self.stats_dict["backlog"]]
            tmp_reward = joint_queue_reward(actions, queues)
            reward += tmp_reward
            # log.info("joint queue: %f " % tmp_reward, end='')
        if "std_dev" in self.reward_model:
            tmp_reward = std_dev_reward(actions)
            reward += tmp_reward
            # log.info("std_dev: %f " % tmp_reward, end='')
        if "fairness" in self.reward_model:
            tmp_reward = fairness_reward(actions)
            reward += tmp_reward
            # log.info("fairness: %f " % tmp_reward, end='')
        # log.info("Total: %f" % reward)
        return reward


# small script to visualize the reward output
if __name__ == '__main__':
    import matplotlib.pyplot as plt
    queues = [i * 0.1 for i in range(0, 11)]
    actions = [i * .001 for i in range(0, 1000)]
    for queue in queues:
        rewards = []
        queue_input = np.array([queue])
        for action in actions:
            action_input = np.array([action])
            rewards.append((joint_queue_reward(action_input, queue_input)))
        plt.plot(actions, rewards, label="Queue Size %f" % queue)
    plt.xlabel('Action Input')
    plt.ylabel('Reward')
    plt.legend()
    plt.show()
