from __future__ import division  # For Python 2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import itertools
import os
import json


MAX_BW = 10e6
STATS_DICT = {"backlog": 0, "olimit": 1,
              "drops": 2, "bw_rx": 3, "bw_tx": 4}
NUM_IFACES = 6


def check_plt_dir(plt_name):
    plt_dir = os.path.dirname(plt_name)
    if not plt_dir == '' and not os.path.exists(plt_dir):
        print("Folder %s does not exist! Creating..." % plt_name)
        os.makedirs(plt_dir)


def running_mean(x, N=100):
    if (len(x) < N):
        return x
    cumsum = np.cumsum(np.insert(x, 0, 0))
    return (cumsum[N:] - cumsum[:-N]) / float(N)


def merge_dict(target, input_dict):
    merged = {}
    for d in (target, input_dict):
        for key, value in d.iteritems():
            merged[key].append(value)
    return merged


def average_dict(input_dict):
    ''' Strips keys and averages the values in each dictionary
     {key1: [val1, val2, val3], key2: [val4, val5, val6]}
     -> [avg(val1, val4), avg(val2, val5), avg(val3, val6)]} '''
    tmp = []
    for key, val in input_dict.items():
        tmp.append(val)
    return np.mean(tmp, axis=0)


def get_iface_ids(key_list, delim):
    ''' Sanitize interface ids according to the given limiter. Removes the
      random string which is usually prepended. '''
    key_list.sort()
    tmp_dict = {}
    for iface_key in key_list:
        iface_id = delim + iface_key.split(delim)[1]
        tmp_dict[iface_id] = []
    return tmp_dict


def get_nested_values_from_dict(dict_list, nested_key):
    ''' Find nested key in dictionary and bring it to the top.
      Destroys the key in the process.
      {key1: {keyx:valx keyy:valy}, key2: {keyx:vala keyy:valb}}
      -> [key1:valx, key2:vala} '''
    tmp = {}
    for top_key in dict_list:
        for d in dict_list[top_key]:
            tmp.setdefault(top_key, []).append(d[nested_key])
    return tmp


def collapse_nested_dict_list(dict_list, delim):
    ''' Take a list of dictionaries and merge them according to their keys.
      [{key1: valx, key2: valy}, {key1: vala, key2: valb}]
      -> {key1: [valx, vala], key2: [valy, valb]}'''
    tmp = {}
    for d in dict_list:
        keys_list = d.keys()
        keys_list.sort()
        for key in keys_list:
            # iface_id = delim + key.split(delim)[1]
            tmp.setdefault(key, []).append(d[key])
    # ret_list = {k: np.mean(tmp[k], axis=0) for k in tmp}
    return tmp


def collapse_nested_array(array_list, dict_len=None):
    ''' Take a list of dictionaries and merge them according to their keys.
      [{key1: valx, key2: valy}, {key1: vala, key2: valb}]
      -> {key1: [valx, vala], key2: [valy, valb]}'''
    tmp = []
    for arr in array_list:
        if dict_len:
            tmp_arr = arr.reshape((NUM_IFACES, dict_len))
        else:
            tmp_arr = arr
        tmp.append(np.average(tmp_arr, axis=0))
    return np.array(tmp)


def get_nested_values_from_array(array_list, nested_key, base_dict):
    ''' Find nested key in dictionary and bring it to the top.
      Destroys the key in the process.
      {key1: {keyx:valx keyy:valy}, key2: {keyx:vala keyy:valb}}
      -> [key1:valx, key2:vala} '''
    tmp = []
    for arr in array_list:
        tmp.append(arr[base_dict[nested_key]])
    return np.array(tmp)


def parse_config(results_dir):
    with open(results_dir + "/test_config.json") as conf_file:
        return json.load(conf_file)


def load_file(filename):
    out = []
    with open(filename, 'rb') as f:
        fsz = os.fstat(f.fileno()).st_size
        while f.tell() < fsz:
            item = np.load(f)
            if item.size > 0:
                out.append(item)
            item = None
    flat_out = [x for sublist in out for x in sublist]
    out = None
    return flat_out


def release_list(l):
    del l[:]
    del l


def plot(data_dir, plot_dir, name):

    # Set seaborn style for plotting
    sns.set(style="white", font_scale=2)

    test_config = parse_config(data_dir)
    algos = test_config["algorithms"]
    runs = test_config["runs"]
    num_timesteps = test_config["timesteps"]
    transports = test_config["transport"]
    topo = test_config["topology"]
    for transport in transports:
        DELIM = "sw"
        if topo is "fattree":
            DELIM = "-"
        # fig, ax = plt.subplots(3, 1)
        fig, ax = plt.subplots(3, 1, figsize=(20, 10))
        ax1 = ax[0]
        ax2 = ax[1]
        ax3 = ax[2]

        mark_iterator = itertools.cycle((".", ",", "o", "v", "^", "<", ">"))
        line_iterator = itertools.cycle(('--', '-.', '-', ':'))
        colour = itertools.cycle(('b', 'g', 'r', 'c', 'm', 'y', 'k', 'w'))
        reward_max = -np.inf
        reward_min = np.inf
        queue_max = 0
        bw_max = 0
        plt_rewards = {}
        plt_actions = {}
        plt_queues = {}
        plt_bandwidths = {}
        plt_overlimits_bar = {}
        plt_drops_bar = {}
        for i, algo in enumerate(algos):
            rewards_list = []
            actions_list = []
            queues_list = []
            bandwidths_list = []
            overlimits_bar_list = []
            drops_bar_list = []
            for index in range(runs):
                run_dir = data_dir + "/%s/run%d" % (transport.lower(), index)
                marker = next(mark_iterator)
                linestyle = next(line_iterator)
                offset = num_timesteps * 0.25 + i * num_timesteps * 0.05
                reward_file = '%s/reward_per_step_%s.npy' % (
                    run_dir, algo.lower())
                actions_file = '%s/action_per_step_by_port_%s.npy' % (
                    run_dir, algo.lower())
                stats_file = '%s/stats_per_step_by_port_%s.npy' % (
                    run_dir, algo.lower())

                print("Computing running reward mean...")
                # rewards
                print("Loading %s..." % reward_file)
                np_rewards = load_file(reward_file)
                rewards = running_mean(np_rewards)
                np_rewards = None
                if rewards.size:
                    rewards_list.append(rewards)
                # actions
                print("Loading %s..." % actions_file)
                np_actions = load_file(actions_file)
                print("Computing running action mean...")
                actions = collapse_nested_array(np_actions)
                np_actions = None
                mean_actions = running_mean(actions) / MAX_BW
                actions = None
                # queues
                print("Loading %s..." % stats_file)
                np_stats = load_file(stats_file)
                if mean_actions.size:
                    actions_list.append(mean_actions)
                print("Computing running queue mean...")
                iface_stats = collapse_nested_array(np_stats, len(STATS_DICT))
                np_stats = None
                queues = get_nested_values_from_array(
                    iface_stats, "backlog", STATS_DICT)
                drops = get_nested_values_from_array(
                    iface_stats, "drops", STATS_DICT)
                overlimits = get_nested_values_from_array(
                    iface_stats, "olimit", STATS_DICT)
                bws = get_nested_values_from_array(
                    iface_stats, "bw_tx", STATS_DICT)
                iface_stats = None
                mean_queues = running_mean(queues)
                mean_bar_overlimits = np.mean(overlimits)
                mean_bar_drops = np.mean(drops)
                queues = None
                overlimits = None
                drops = None
                if mean_queues.size:
                    queues_list.append(mean_queues)
                    drops_bar_list.append(mean_bar_drops)
                    overlimits_bar_list.append(mean_bar_overlimits)
                mean_queues = None
                mean_bar_overlimits = None
                mean_bar_drops = None
                # bandwidths
                mean_bw = 10 * running_mean(bws) / MAX_BW
                bws = None
                if mean_bw.size:
                    bandwidths_list.append(mean_bw)
            plt_rewards[algo] = np.mean(rewards_list, axis=0)
            rewards_list = None
            plt_actions[algo] = np.mean(actions_list, axis=0)
            actions_list = None
            plt_queues[algo] = np.mean(queues_list, axis=0)
            queues_list = None
            plt_overlimits_bar[algo] = np.mean(overlimits_bar_list, axis=0)
            overlimits_bar_list = None
            plt_drops_bar[algo] = np.mean(drops_bar_list, axis=0)
            drops_bar_list = None
            plt_bandwidths[algo] = np.mean(bandwidths_list, axis=0)
            bandwidths_list = None

            if np.amax(plt_rewards[algo]) > reward_max:
                reward_max = np.amax(plt_rewards[algo])
            if np.amin(plt_rewards[algo]) < reward_min:
                reward_min = np.amin(plt_rewards[algo])
            if np.amax(plt_queues[algo]) > queue_max:
                queue_max = np.amax(plt_queues[algo])
            if np.amax(plt_bandwidths[algo]) > bw_max:
                bw_max = np.amax(plt_bandwidths[algo])

        for i, algo in enumerate(algos):
            if algo not in plt_rewards:
                break
            marker = next(mark_iterator)
            linestyle = next(line_iterator)
            offset = num_timesteps / 4 + i * num_timesteps / 10
            linewidth = 2
            normalized_reward = (plt_rewards[algo] -
                                 reward_min) / (reward_max - reward_min)
            normalized_queues = plt_queues[algo] / queue_max
            normalized_bw = plt_bandwidths[algo] / bw_max
            if algo.lower() == "pg":
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
        # ax1.set_ylim([0.2, 1.15])
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
        plt_name = "%s/" % (plot_dir)
        plt_name += "%s" % name
        plt_name += "_%s" % topo
        plt_name += "_%s" % transport
        plt_name += "_%s" % num_timesteps
        print("Saving plot %s" % plt_name)
        check_plt_dir(plt_name)
        plt.savefig(plt_name + ".pdf")
        plt.savefig(plt_name + ".png")
        plt.gcf().clear()

        fig, ax = plt.subplots(2, 1, figsize=(20, 10))
        ax_overlimits = ax[0]
        ax_drops = ax[1]
        ax_overlimits.set_ylabel('drop avg')
        ax_drops.set_ylabel('overlimit avg')
        ax_overlimits.get_xaxis().set_visible(False)
        X = np.arange(len(plt_overlimits_bar))
        ax_overlimits.bar(X, plt_overlimits_bar.values(),
                          tick_label=plt_overlimits_bar.keys())
        ax_drops.bar(X, plt_drops_bar.values(),
                     tick_label=plt_drops_bar.keys())
        plt.savefig(plt_name + "_bar.pdf")
        plt.savefig(plt_name + "_bar.png")
        plt.gcf().clear()


if __name__ == '__main__':
    PLOT_DIR = os.path.dirname(os.path.abspath(__file__)) + "/plots"
    ROOT = "data"
    for folder in next(os.walk(ROOT))[1]:
        print("Crawling folder %s " % folder)
        machinedir = ROOT + "/" + folder
        plot(machinedir, PLOT_DIR, folder)
