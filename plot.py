from __future__ import division  # For Python 2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import itertools
import os
import json
import numpy as np
import seaborn as sns
from filelock import FileLock


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


def plot_barchart(plt_stats, plt_name):
    algos = plt_stats.keys()
    fig, ax = plt.subplots(2, 1, figsize=(20, 10))
    ax_overlimits = ax[0]
    ax_drops = ax[1]
    ax_overlimits.set_ylabel('drop avg')
    ax_drops.set_ylabel('overlimit avg')
    ax_overlimits.get_xaxis().set_visible(False)
    bar_overlimits = []
    bar_drops = []
    bar_labels = []
    for algo in algos:
        bar_overlimits.append(plt_stats[algo]["overlimits"])
        bar_drops.append(plt_stats[algo]["drops"])
        bar_labels.append(algo)
    ax_overlimits.bar(range(len(bar_labels)), bar_overlimits,
                      tick_label=bar_labels)
    ax_drops.bar(range(len(bar_labels)), bar_drops, tick_label=bar_labels)
    plt.savefig(plt_name + "_bar.pdf")
    plt.savefig(plt_name + "_bar.png")
    plt.gcf().clear()


def plot_lineplot(plt_stats, num_timesteps, plt_name):
    algos = plt_stats.keys()

    # get the maximum values of
    reward_max = -np.inf
    reward_min = np.inf
    queue_max = 0
    bw_max = 0

    for i, algo in enumerate(algos):
        if np.amax(plt_stats[algo]["rewards"]) > reward_max:
            reward_max = np.amax(plt_stats[algo]["rewards"])
        if np.amin(plt_stats[algo]["rewards"]) < reward_min:
            reward_min = np.amin(plt_stats[algo]["rewards"])
        if np.amax(plt_stats[algo]["queues"]) > queue_max:
            queue_max = np.amax(plt_stats[algo]["queues"])
        if np.amax(plt_stats[algo]["bws"]) > bw_max:
            bw_max = np.amax(plt_stats[algo]["bws"])
    mean_smoothing = num_timesteps / 100

    fig, ax = plt.subplots(3, 1, figsize=(20, 10))
    mark_iterator = itertools.cycle((".", ",", "o", "v", "^", "<", ">"))
    line_iterator = itertools.cycle(('--', '-.', '-', ':'))
    colour = itertools.cycle(('b', 'g', 'r', 'c', 'm', 'y', 'k', 'w'))
    for i, algo in enumerate(algos):
        marker = next(mark_iterator)
        linestyle = next(line_iterator)
        offset = int(num_timesteps * 0.01 + i * num_timesteps * 0.01)
        linewidth = 2
        normalized_reward = running_mean((plt_stats[algo]["rewards"] -
                                          reward_min) / (reward_max - reward_min), mean_smoothing)
        normalized_queues = running_mean(
            plt_stats[algo]["queues"], mean_smoothing)
        if queue_max:
            normalized_queues /= queue_max
        normalized_bw = running_mean(plt_stats[algo]["bws"], mean_smoothing)
        if bw_max:
            normalized_bw /= bw_max
        ax[0].plot(normalized_reward, label=algo, linewidth=linewidth,
                   linestyle=linestyle, marker=marker, markevery=offset)
        ax[1].plot(normalized_queues, label=algo,
                   linestyle=linestyle, marker=marker,
                   markevery=offset, linewidth=linewidth)
        ax[2].plot(normalized_bw, label=algo, linestyle=linestyle,
                   marker=marker, markevery=offset, linewidth=linewidth)

    ax[0].set_ylabel('rewards')
    ax[1].set_ylabel('queue length')
    ax[2].set_ylabel('bandwidth')
    ax[0].get_xaxis().set_visible(False)
    ax[1].get_xaxis().set_visible(False)
    ax[2].set_xlabel('timestep')
    # ax[0].set_ylim([0.2, 1.15])
    # ax[1].set_ylim([-0.15, 1.15])
    # ax[2].set_ylim([-0.15, 1.15])
    ax[0].margins(y=0.15)
    ax[1].margins(y=0.05)
    ax[2].margins(y=0.15)
    ax[0].set_xlim([0, num_timesteps])
    ax[1].set_xlim([0, num_timesteps])
    ax[2].set_xlim([0, num_timesteps])
    tcks = ax[2].get_xticks()
    tcks[-1] = num_timesteps
    ax[2].set_xticks(tcks)
    fig.subplots_adjust(hspace=0.1, left=0.12, right=0.95)
    handles, labels = ax[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper center', fancybox=True,
               shadow=True, ncol=len(algos))
    print("Saving plot %s" % plt_name)
    check_plt_dir(plt_name)
    plt.savefig(plt_name + ".pdf")
    plt.savefig(plt_name + ".png")
    plt.gcf().clear()


def preprocess_data(algos, runs, transport_dir):
    plt_stats = {}
    for i, algo in enumerate(algos):
        plt_stats[algo] = {"rewards": {}, "actions": {}, "queues": {},
                           "bws": {}, "overlimits": {}, "drops": {}}
        run_list = dict((key, []) for key in plt_stats[algo].keys())
        for index in range(runs):
            run_dir = transport_dir + "/run%d" % index
            stats_file = '%s/runtime_statistics_%s.npy' % (
                run_dir, algo.lower())
            print("Loading %s..." % stats_file)
            with FileLock(stats_file + ".lock"):
                try:
                    statistics = np.load(stats_file).item()
                except Exception:
                    print("Error loading file %s" % stats_file)
                    exit(1)
            rewards = np.array(statistics["reward"])
            host_actions = np.moveaxis(statistics["actions"], 0, -1)
            port_stats = np.moveaxis(statistics["stats"], 0, -1)
            port_queues = np.array(port_stats[STATS_DICT["backlog"]])
            port_bws = np.array(port_stats[STATS_DICT["bw_tx"]])
            port_overlimits = np.array(port_stats[STATS_DICT["olimit"]])
            port_drops = np.array(port_stats[STATS_DICT["drops"]])
            # rewards
            if rewards.size:
                run_list["rewards"].append(rewards)
            # actions
            actions = host_actions.mean(axis=0)
            if actions.size:
                run_list["actions"].append(actions)
            # queues
            flat_queues = port_queues.mean(axis=0)
            if flat_queues.size:
                run_list["queues"].append(flat_queues)
            # bandwidths
            flat_bw = port_bws.mean(axis=0)
            if flat_bw.size:
                run_list["bws"].append(flat_bw)
            # overlimits
            mean_overlimits = port_overlimits.mean()
            if mean_overlimits.size:
                run_list["overlimits"].append(mean_overlimits)
            # drops
            mean_drops = port_drops.mean()
            if mean_drops.size:
                run_list["drops"].append(mean_drops)

        # average over all runs
        for stat in run_list.keys():
            plt_stats[algo][stat] = np.mean(run_list[stat], axis=0)
    return plt_stats


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
        transport_dir = data_dir + "/%s" % (transport.lower())
        plt_stats = preprocess_data(algos, runs, transport_dir)
        plt_name = "%s/" % (plot_dir)
        plt_name += "%s" % name
        plt_name += "_%s" % topo
        plt_name += "_%s" % transport
        plt_name += "_%s" % num_timesteps
        plot_lineplot(plt_stats, num_timesteps, plt_name)
        plot_barchart(plt_stats, plt_name)


if __name__ == '__main__':
    PLOT_DIR = os.path.dirname(os.path.abspath(__file__)) + "/plots"
    ROOT = "results"
    for folder in next(os.walk(ROOT))[1]:
        print("Crawling folder %s " % folder)
        machinedir = ROOT + "/" + folder
        plot(machinedir, PLOT_DIR, folder)
