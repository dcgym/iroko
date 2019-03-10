from __future__ import division  # For Python 2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import itertools
import os
import json
import argparse
import numpy as np
import pandas as pd
import seaborn as sns
from filelock import FileLock

MAX_BW = 10e6
STATS_DICT = {"backlog": 0, "olimit": 1,
              "drops": 2, "bw_rx": 3, "bw_tx": 4}

PLOT_DIR = os.path.dirname(os.path.abspath(__file__)) + "/plots"
ROOT = "results"

PARSER = argparse.ArgumentParser()
PARSER.add_argument('--input', '-i', dest='input_dir')
ARGS = PARSER.parse_args()


def check_plt_dir(plt_name):
    plt_dir = os.path.dirname(plt_name)
    if not plt_dir == '' and not os.path.exists(plt_dir):
        print("Folder %s does not exist! Creating..." % plt_name)
        os.makedirs(plt_dir)


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


def np_dict_to_pd(np_dict, key, df_type="float64"):
    pd_frame = pd.DataFrame(
        {k: pd.Series(v) for k, v in np_dict[key].items()})
    return pd_frame.astype(df_type)


def plot_barchart(algos, plt_stats, plt_name):
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
        bar_overlimits.append(plt_stats["olimit"][algo])
        bar_drops.append(plt_stats["drops"][algo])
        bar_labels.append(algo)
    ax_overlimits.bar(range(len(bar_labels)), bar_overlimits,
                      tick_label=bar_labels)
    ax_drops.bar(range(len(bar_labels)), bar_drops, tick_label=bar_labels)
    plt.savefig(plt_name + "_bar.pdf")
    plt.savefig(plt_name + "_bar.png")
    plt.gcf().clear()


def plot_lineplot(algos, plt_stats, timesteps, plt_name):
    # Set seaborn style for plotting
    sns.set(style="white", font_scale=2)
    mean_smoothing = int(timesteps / 100)

    print("Converting numpy arrays into pandas dataframes.")
    # rewards_pd = pd.DataFrame.from_dict(
    #     plt_stats["rewards"], orient='index').astype('float64').transpose()
    rewards_pd = np_dict_to_pd(plt_stats, "rewards")
    actions_pd = np_dict_to_pd(plt_stats, "actions")
    queues_pd = np_dict_to_pd(plt_stats, "backlog")
    bws_pd = np_dict_to_pd(plt_stats, "bw_tx")
    print("Computing overlimit deltas.")
    olimit_pd = np_dict_to_pd(plt_stats, "olimit").diff()
    print("Computing drops deltas.")
    drops_pd = np_dict_to_pd(plt_stats, "drops").diff()

    # get the maximum and minimum values
    # reward_max = rewards_pd.max().max()
    # reward_min = rewards_pd.min().min()
    # queue_max = queues_pd.max().max()
    # bw_max = bws_pd.max().max()
    print("Computing rolling reward.")
    rolling_reward = rewards_pd.rolling(mean_smoothing).mean()
    # normalized_reward = (
    #     rolling_reward - rolling_reward.mean()) / rolling_reward.std()
    print("Computing rolling actions.")
    rolling_actions = actions_pd.rolling(mean_smoothing).mean()
    print("Computing rolling queues.")
    rolling_queue = queues_pd.rolling(mean_smoothing).mean()
    print("Computing rolling bandwidth.")
    rolling_bw = bws_pd.rolling(mean_smoothing).mean()
    print("Computing rolling overlimits.")
    rolling_olimit = olimit_pd.rolling(mean_smoothing).mean()
    print("Computing rolling drops.")
    rolling_drops = drops_pd.rolling(mean_smoothing).mean()

    markers = (".", ",", "o", "v", "^", "<", ">")
    linestyles = ('--', '-.', '-', ':')
    colours = ('b', 'g', 'r', 'c', 'm', 'y', 'k', 'w')
    mark_iterator = itertools.cycle(markers)
    line_iterator = itertools.cycle(linestyles)
    colour = itertools.cycle(colours)
    print("Plotting lines.")
    fig, ax = plt.subplots(6, 1, figsize=(20, 10))
    # ax[0] = rolling_reward.plot(ax=ax[0], legend=False)
    # ax[1] = rolling_actions.plot(ax=ax[1], legend=False)
    # ax[2] = rolling_queue.plot(ax=ax[2], legend=False)
    # ax[3] = rolling_bw.plot(ax=ax[3], legend=False)
    # ax[4] = rolling_olimit.plot(ax=ax[4], legend=False)
    # ax[5] = rolling_drops.plot(ax=ax[5], legend=False)
    ax[0] = sns.lineplot(data=rolling_reward,
                         ax=ax[0], legend=False)
    ax[1] = sns.lineplot(data=rolling_actions,
                         ax=ax[1], legend=False)
    ax[2] = sns.lineplot(data=rolling_queue,
                         ax=ax[2], legend=False)
    ax[3] = sns.lineplot(data=rolling_bw,
                         ax=ax[3], legend=False)
    ax[4] = sns.lineplot(data=rolling_olimit,
                         ax=ax[4], legend=False)
    ax[5] = sns.lineplot(data=rolling_drops,
                         ax=ax[5], legend=False)
    # for i, algo in enumerate(algos):
    #     marker = next(mark_iterator)
    #     linestyle = next(line_iterator)
    #     offset = int(timesteps * 0.01 + i * timesteps * 0.01)
    #     linewidth = 2
    #     normalized_reward = running_mean((plt_stats["rewards"][algo] -
    #                                       reward_min) / (reward_max - reward_min), mean_smoothing)
    #     normalized_queues = running_mean(
    #         plt_stats["backlog"][algo], mean_smoothing)
    #     if queue_max:
    #         normalized_queues /= queue_max
    #     normalized_bw = running_mean(plt_stats["bw_tx"][algo], mean_smoothing)
    #     if bw_max:
    #         normalized_bw /= bw_max
    #     ax[0].plot(normalized_reward, label=algo, linewidth=linewidth,
    #                linestyle=linestyle, marker=marker, markevery=offset)
    #     ax[1].plot(normalized_queues, label=algo,
    #                linestyle=linestyle, marker=marker,
    #                markevery=offset, linewidth=linewidth)
    #     ax[2].plot(normalized_bw, label=algo, linestyle=linestyle,
    #                marker=marker, markevery=offset, linewidth=linewidth)

    num_subplots = len(ax)
    ax[0].set_ylabel('rewards')
    ax[1].set_ylabel('actions')
    ax[2].set_ylabel('queue length')
    ax[3].set_ylabel('bandwidth')
    ax[4].set_ylabel('overlimits')
    ax[5].set_ylabel('drops')
    ax[0].get_xaxis().set_visible(False)
    ax[1].get_xaxis().set_visible(False)
    ax[2].get_xaxis().set_visible(False)
    ax[3].get_xaxis().set_visible(False)
    ax[4].get_xaxis().set_visible(False)
    ax[num_subplots - 1].set_xlabel('time')
    # for subplot in ax:
    #     subplot.set_xlim([0, timesteps])
    # ax[0].set_ylim([0.2, 1.15])
    # ax[1].set_ylim([-0.15, 1.15])
    # ax[2].set_ylim([-0.15, 1.15])
    # ax[0].margins(y=0.15)
    # ax[1].margins(y=0.05)
    # ax[2].margins(y=0.15)
    # tcks = ax[num_subplots - 1].get_xticks()
    # tcks[-1] = timesteps
    # ax[num_subplots - 1].set_xticks(tcks)
    # fig.subplots_adjust(hspace=0.1, left=0.12, right=0.95)
    fig.legend(rewards_pd.columns.values, loc='upper center', fancybox=True,
               shadow=True, ncol=len(algos))
    print("Saving plot %s" % plt_name)
    check_plt_dir(plt_name)
    plt.savefig(plt_name + ".pdf")
    plt.savefig(plt_name + ".png")
    plt.gcf().clear()


def preprocess_data(algo, runs, transport_dir, timesteps):
    run_list = {"rewards": [], "actions": [], "backlog": [],
                "bw_tx": [], "bw_rx": [], "olimit": [], "drops": []}
    for index in range(runs):
        run_dir = transport_dir + "run%d" % index
        stats_file = '%s/%s/runtime_statistics.npy' % (
            run_dir, algo.lower())
        print("Loading %s..." % stats_file)
        with FileLock(stats_file + ".lock"):
            try:
                statistics = np.load(stats_file).item()
            except Exception as e:
                print("Error loading file %s" % stats_file, e)
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
            run_list["rewards"].append(rewards[:timesteps])
        # actions
        print("Computing mean of host actions per step.")
        actions = host_actions.mean(axis=0)
        if actions.size:
            run_list["actions"].append(actions[:timesteps])
        # queues
        print("Computing mean of interface queues per step.")
        flat_queues = port_queues.mean(axis=0)
        if flat_queues.size:
            run_list["backlog"].append(flat_queues[:timesteps])
        # bandwidths
        print("Computing mean of interface bandwidth per step.")
        flat_bw = port_bws.mean(axis=0)
        if flat_bw.size:
            run_list["bw_tx"].append(flat_bw[:timesteps])
        # overlimits
        print("Computing mean of interface overlimits per step.")
        mean_overlimits = port_overlimits.mean(axis=0)
        if mean_overlimits.size:
            run_list["olimit"].append(mean_overlimits[:timesteps])
        # drops
        mean_drops = port_drops.mean(axis=0)
        print("Computing mean of interface drops per step.")
        if mean_drops.size:
            run_list["drops"].append(mean_drops[:timesteps])

    return run_list


def plot(data_dir, plot_dir, name):

    test_config = parse_config(data_dir)
    rl_algos = test_config["rl_algorithms"]
    tcp_algos = test_config["tcp_algorithms"]
    algos = rl_algos + tcp_algos
    runs = test_config["runs"]
    timesteps = test_config["timesteps"]
    transports = test_config["transport"]
    topo = test_config["topology"]
    for transport in transports:
        plt_stats = {"rewards": {}, "actions": {}, "backlog": {},
                     "bw_tx": {}, "bw_rx": {}, "olimit": {}, "drops": {}}
        for algo in algos:
            if (algo in tcp_algos):
                transport_dir = data_dir + "/tcp_"
            else:
                transport_dir = data_dir + "/%s_" % (transport.lower())
            run_list = preprocess_data(algo, runs, transport_dir, timesteps)
            # average over all runs
            for stat in run_list.keys():
                plt_stats[stat][algo] = np.mean(run_list[stat], axis=0)
        plt_name = "%s/" % (plot_dir)
        plt_name += "%s" % name
        plt_name += "_%s" % topo
        plt_name += "_%s" % transport
        plt_name += "_%s" % timesteps
        plot_lineplot(algos, plt_stats, timesteps, plt_name)
        # plot_barchart(algos, plt_stats, plt_name)


if __name__ == '__main__':

    if ARGS.input_dir:
        plot(ARGS.input_dir, PLOT_DIR, os.path.basename(
            os.path.normpath(ARGS.input_dir)))
        exit(0)

    for folder in next(os.walk(ROOT))[1]:
        print("Crawling folder %s " % folder)
        machinedir = ROOT + "/" + folder
        plot(machinedir, PLOT_DIR, folder)
