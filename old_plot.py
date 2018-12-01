import matplotlib
matplotlib.use('Agg')
import argparse
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import itertools
import os

PARSER = argparse.ArgumentParser()
PARSER.add_argument('--env', '-e', dest='env',
                    default='iroko', help='The platform to run.')
PARSER.add_argument('--topo', '-to', dest='topo',
                    default='dumbbell', help='The topology to operate on.')


def check_plt_dir(plt_name):
    plt_dir = os.path.dirname(plt_name)
    if not plt_dir == '' and not os.path.exists(plt_dir):
        print("Folder %s does not exist! Creating..." % plt_name)
        os.makedirs(plt_dir)


MAX_BW = 10e6


def moving_average(a, n=250):
    ret = np.cumsum(a, dtype=float)
    ret[n:] = ret[n:] - ret[:-n]
    return ret[n - 1:] / n


def merge_dict(target, input_dict):
    merged = {}
    for d in (target, input_dict):
        for key, value in d.iteritems():
            merged[key].append(value)
    return merged


def average_dict_list(dict_list):
    if not dict_list:
        return
    keys = dict_list[0].keys()
    tmp = {k: [] for k in keys}
    for k in keys:
        for l in dict_list:
            tmp[k].append(l[k])
    dict_list = {k: np.average(tmp[k], axis=0) for k in tmp}
    return dict_list


def plot(algos, runs, data_dir, plot_dir, name):

    # sns.set(font_scale=2)
    sns.set_style("white")
    # fig, ax = plt.subplots(3, 1, figsize=(16, 10))
    fig, ax = plt.subplots(3, 1)
    ax1 = ax[0]
    ax2 = ax[1]
    ax3 = ax[2]
    mark_iterator = itertools.cycle((1, 2, 3, 4, 6, 7, 8, 9, 10))
    line_iterator = itertools.cycle(('--', '-.', '-', ':'))
    colour = itertools.cycle(('b', 'g', 'r', 'c', 'm', 'y', 'k', 'w'))
    num_timesteps = 0
    reward_max = -np.inf
    reward_min = np.inf
    queue_max = 0
    bw_max = 0
    plt_rewards = {}
    plt_actions = {}
    plt_queues = {}
    plt_bandwidths = {}
    for i, algo in enumerate(algos):
        rewards_list = []
        actions_list = []
        queues_list = []
        bandwidths_list = []
        for index in range(runs):
            reward_file = '%s/reward_per_step_%s%d.npy' % (
                data_dir, algo, index)
            actions_file = '%s/action_per_step_by_port_%s%d.npy' % (
                data_dir, algo, index)
            queue_file = '%s/queues_per_step_by_port_%s%d.npy' % (
                data_dir, algo, index)
            bw_file = '%s/bandwidths_per_step_by_port_%s%d.npy' % (
                data_dir, algo, index)
            if not os.path.isfile(reward_file):
                continue
            print ("Loading %s..." % reward_file)
            np_rewards = np.load(reward_file)
            if len(np_rewards) != 0:
                rewards_list.append(np_rewards)
            print ("Loading %s..." % actions_file)
            np_actions = np.load(actions_file).item()
            if len(np_actions) != 0:
                actions_list.append(np_actions)
            print ("Loading %s..." % queue_file)
            np_queues = np.load(queue_file).item()
            if len(np_queues) != 0:
                queues_list.append(np_queues)
            print ("Loading %s..." % bw_file)
            np_bws = np.load(bw_file).item()["tx"]
            if len(np_bws) != 0:
                bandwidths_list.append(np_bws)

        if not rewards_list:
            break
        # rewards
        rewards = np.average(rewards_list, axis=0)
        plt_rewards[algo] = moving_average(rewards)
        if(np.amax(plt_rewards[algo]) > reward_max):
            reward_max = np.amax(plt_rewards[algo])
        if(np.amin(plt_rewards[algo]) < reward_min):
            reward_min = np.amin(plt_rewards[algo])
        # actions
        actions = average_dict_list(actions_list)
        plt_actions[algo] = average_dict_list(actions_list)
        # queues
        queues = average_dict_list(queues_list)
        mean_queues = np.average(queues.values(), axis=0) / MAX_BW
        plt_queues[algo] = moving_average(mean_queues)
        if(np.amax(plt_queues[algo]) > queue_max):
            queue_max = np.amax(plt_queues[algo])
        # bandwidths
        bandwidths = average_dict_list(bandwidths_list)
        mean_bw = 10 * np.average(bandwidths.values(), axis=0) / MAX_BW
        plt_bandwidths[algo] = moving_average(mean_bw)
        if(np.amax(plt_bandwidths[algo]) > bw_max):
            bw_max = np.amax(plt_bandwidths[algo])

    for i, algo in enumerate(algos):
        if algo not in plt_rewards:
            break
        marker = mark_iterator.next()
        linestyle = line_iterator.next()
        offset = 2500 + i * 500
        linewidth = 1
        num_timesteps = len(plt_queues[algo])
        normalized_reward = (plt_rewards[algo] -
                             reward_min) / (reward_max - reward_min)
        normalized_queues = plt_queues[algo] / queue_max
        normalized_bw = plt_bandwidths[algo] / bw_max
        if algo == "PG":
            algo = "REINFORCE"

        ax1.plot(normalized_reward, label=algo, linewidth=linewidth,
                 linestyle=linestyle, marker=marker, markevery=offset)
        ax2.plot(normalized_queues, label=algo,
                 linestyle=linestyle, marker=marker,
                 markevery=offset, linewidth=linewidth)
        ax3.plot(normalized_bw, label=algo, linestyle=linestyle,
                 marker=marker, markevery=offset, linewidth=linewidth)

    ax1.set_ylabel('rewards')
    ax2.set_ylabel('queue length')
    ax3.set_ylabel('bandwidth')
    ax1.get_xaxis().set_visible(False)
    ax2.get_xaxis().set_visible(False)
    ax3.set_xlabel('timestep')
    # ax1.set_ylim([-0.15, 1.15])
    # ax2.set_ylim([-0.15, 1.15])
    # ax3.set_ylim([-0.15, 1.15])
    ax1.margins(y=0.15)
    ax2.margins(y=0.05)
    ax3.margins(y=0.15)
    ax1.set_xlim([0, num_timesteps])
    ax2.set_xlim([0, num_timesteps])
    ax3.set_xlim([0, num_timesteps])
    tcks = ax3.get_xticks()
    tcks[-1] = num_timesteps
    ax3.set_xticks(tcks)
    fig.subplots_adjust(hspace=0.1, left=0.12, right=0.95)
    handles, labels = ax1.get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', fancybox=True,
               shadow=True, ncol=5)
    plt_name = "%s/%s" % (plot_dir, name)
    check_plt_dir(plt_name)
    plt.savefig(plt_name + ".pdf")
    plt.savefig(plt_name + ".png")
    plt.gcf().clear()


if __name__ == '__main__':
    ALGOS = ["DDPG", "PG", "PPO", "TCP_NV", "DCTCP"]
    RUNS = 5
    PLOT_DIR = os.path.dirname(os.path.abspath(__file__)) + "/plots/"
    root = "dc_gym/data_old"
    for folder in os.listdir(root):
        machinedir = root + "/" + folder
        for subfolder in os.listdir(machinedir):
            datadir = machinedir + "/" + subfolder
            plot(ALGOS, RUNS, datadir, PLOT_DIR + folder, subfolder)
