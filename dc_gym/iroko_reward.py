import numpy as np
import math
import logging
log = logging.getLogger(__name__)


def fairness_reward(actions, queues=None):
    """Compute Jain"s fairness index for a list of values.
    See http://en.wikipedia.org/wiki/Fairness_measure for fairness equations.
    @param values: list of values
    @return fairness: JFI
    """
    if len(actions) == 0:
        return 1.0
    num = sum(actions) ** 2
    denom = len(actions) * sum([i ** 2 for i in actions])
    return num / float(denom)


def action_reward(actions, queues=None):
    return np.mean(actions)


def joint_queue_reward(actions, queues):
    queue = np.max(queues)
    action = action_reward(actions, queues)
    reward = action - 2 * (action * queue)
    return reward * fairness_reward(actions[actions < 1.0])


def step_reward(actions, queues):
    queue = np.max(queues)
    action = np.mean(actions)
    if queue > 0.50:
        return (1 - action)
    else:
        return action + (1 - queue)


def std_dev_reward(actions, queues=None):
    return -np.std(actions)


def queue_reward(actions, queues):
    queue_reward = -np.sum(queues)**2
    return queue_reward


def selu_reward(reward):
    alpha = 1.6732632423543772848170429916717
    scale = 1.0507009873554804934193349852946
    return scale * (max(0, reward) + min(0, alpha * (math.exp(reward) - 1)))


class RewardFunction:
    __slots__ = ["stats_dict", "reward_funs"]

    def __init__(self, reward_models, stats_dict):
        self.stats_dict = stats_dict
        self.reward_funs = self._set_reward(reward_models)

    def _set_reward(self, reward_models):
        reward_funs = []
        for model in reward_models:
            reward_funs.append(globals()["%s_reward" % model])
        return reward_funs

    def get_reward(self, stats, actions):
        queues = stats[self.stats_dict["backlog"]]
        reward = 0.0
        for reward_fun in self.reward_funs:
            reward += reward_fun(actions, queues)
        return reward


# small script to visualize the reward output
if __name__ == "__main__":
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
    plt.xlabel("Action Input")
    plt.ylabel("Reward")
    plt.legend()
    plt.show()
