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
NUM_ACTIONS = 4


def check_plt_dir(plt_name):
    plt_dir = os.path.dirname(plt_name)
    if not plt_dir == '' and not os.path.exists(plt_dir):
        print("Folder %s does not exist! Creating..." % plt_name)
        os.makedirs(plt_dir)


def running_mean(x, N=100):
    if (len(x) < N or N < 1):
        return x
    cumsum = np.cumsum(np.insert(x, 0, 0))
    return (cumsum[int(N):] - cumsum[:-int(N)]) / float(N)


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
    return np.array(flat_out)


def plot(data_dir, plot_dir, name):

    # Set seaborn style for plotting
    sns.set(style="white", font_scale=2)

    test_config = parse_config(data_dir)
    algos = test_config["algorithms"]
    runs = test_config["runs"]
    num_timesteps = test_config["timesteps"]
    mean_smoothing = num_timesteps / 100
    transports = test_config["transport"]
    topo = test_config["topology"]
    for transport in transports:
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
        plt_overlimits = {}
        plt_drops = {}
        for i, algo in enumerate(algos):
            rewards_list = []
            actions_list = []
            queues_list = []
            bandwidths_list = []
            overlimits_list = []
            drops_list = []
            for index in range(runs):
                run_dir = data_dir + "/%s/run%d" % (transport.lower(), index)
                stats_file = '%s/runtime_statistics_%s.npy' % (
                    run_dir, algo.lower())
                print("Loading %s..." % stats_file)
                statistics = np.load(stats_file).item()
                np_rewards = np.array(statistics["reward"])
                np_actions = np.array(statistics["actions"]).transpose()
                np_stats = np.array(statistics["stats"]).transpose()
                queues = np.array(np_stats[STATS_DICT["backlog"]])
                overlimits = np.array(np_stats[STATS_DICT["olimit"]])
                drops = np.array(np_stats[STATS_DICT["drops"]])
                bws = np.array(np_stats[STATS_DICT["bw_tx"]])
                # rewards
                print("Computing running reward mean...")
                rewards = running_mean(np_rewards, mean_smoothing)
                if rewards.size:
                    rewards_list.append(rewards)
                # actions
                print("Computing running action mean...")
                actions = np_actions.mean(axis=0)
                mean_actions = running_mean(actions, mean_smoothing) / MAX_BW
                if mean_actions.size:
                    actions_list.append(mean_actions)
                # queues
                flat_queues = queues.mean(axis=0)
                print("Computing running queue mean...")
                mean_queues = running_mean(flat_queues, mean_smoothing)
                if mean_queues.size:
                    queues_list.append(mean_queues)
                # overlimits
                print("Computing overall overlimit mean...")
                mean_overlimits = overlimits.mean()
                if mean_overlimits.size:
                    overlimits_list.append(mean_overlimits)
                # drops
                print("Computing overall drops mean...")
                mean_drops = drops.mean()
                if mean_drops.size:
                    drops_list.append(mean_drops)
                # bandwidths
                flat_bw = bws.mean(axis=0)
                mean_bw = 10 * running_mean(flat_bw, mean_smoothing) / MAX_BW
                if mean_bw.size:
                    bandwidths_list.append(mean_bw)

            # average over all runs
            plt_rewards[algo] = np.mean(rewards_list, axis=0)
            plt_actions[algo] = np.mean(actions_list, axis=0)
            plt_queues[algo] = np.mean(queues_list, axis=0)
            plt_overlimits[algo] = np.mean(overlimits_list, axis=0)
            plt_drops[algo] = np.mean(drops_list, axis=0)
            plt_bandwidths[algo] = np.mean(bandwidths_list, axis=0)

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
            offset = num_timesteps * 0.25 + i * num_timesteps * 0.05
            linewidth = 2
            normalized_reward = (plt_rewards[algo] -
                                 reward_min) / (reward_max - reward_min)
            normalized_queues = plt_queues[algo]
            if queue_max:
                normalized_queues /= queue_max
            normalized_bw = plt_bandwidths[algo]
            if bw_max:
                normalized_bw /= bw_max
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
                   shadow=True, ncol=len(algos))
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
        X = np.arange(len(plt_overlimits))
        ax_overlimits.bar(X, plt_overlimits.values(),
                          tick_label=plt_overlimits.keys())
        ax_drops.bar(X, plt_drops.values(),
                     tick_label=plt_drops.keys())
        plt.savefig(plt_name + "_bar.pdf")
        plt.savefig(plt_name + "_bar.png")
        plt.gcf().clear()


if __name__ == '__main__':
    PLOT_DIR = os.path.dirname(os.path.abspath(__file__)) + "/plots"
    ROOT = "results"
    for folder in next(os.walk(ROOT))[1]:
        print("Crawling folder %s " % folder)
        machinedir = ROOT + "/" + folder
        plot(machinedir, PLOT_DIR, folder)
