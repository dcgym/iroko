from __future__ import division  # For Python 2
import itertools
import os
import json
import argparse
import numpy as np
import pandas as pd
from filelock import FileLock
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

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


def compute_rolling_df_mean(pd_df, roll):
    rolling_df = pd_df.rolling(roll).mean().dropna()
    return rolling_df.reset_index(drop=True)


def normalize_df_min_max(pd_df):
    df_max = np.nanmax(pd_df.values)
    df_min = np.nanmin(pd_df.values)
    normalized_df = (pd_df - df_min) / (df_max - df_min)
    return normalized_df


def normalize_df_z_score(pd_df):
    df_mean = np.mean(pd_df.values)
    df_std = np.std(pd_df.values)
    normalized_df = (pd_df - df_mean) / df_std
    return normalized_df


def plot_lineplot(algos, plt_stats, timesteps, plt_name):
    # Set seaborn style for plotting
    sns.set(style="ticks", rc={"lines.linewidth": 1.2,
                               "axes.spines.right": False,
                               "axes.spines.top": False,
                               'lines.markeredgewidth': 0.1, })
    # sns.set_context("paper")
    metrics = {}
    plt_metrics = ["reward", "queues", "bw", "drops"]
    print("Converting numpy arrays into pandas dataframes.")
    metrics["reward"] = np_dict_to_pd(plt_stats, "rewards")
    metrics["actions"] = np_dict_to_pd(plt_stats, "actions")
    metrics["queues"] = np_dict_to_pd(plt_stats, "backlog")
    metrics["bw"] = np_dict_to_pd(plt_stats, "bw_tx")
    print("Computing overlimit deltas.")
    metrics["overlimits"] = np_dict_to_pd(plt_stats, "olimit").diff()
    print("Computing drops deltas.")
    metrics["drops"] = np_dict_to_pd(plt_stats, "drops").diff()

    fig, ax = plt.subplots(len(plt_metrics), 1, sharex=True, squeeze=True)
    mean_smoothing = int(timesteps / 100)
    sample = int(timesteps / 10)
    num_subplots = len(ax)
    # newdict = {(k1, k2): v2 for k1, v1 in plt_stats.items()
    #            for k2, v2 in plt_stats[k1].items()}
    # df = pd.DataFrame([newdict[i] for i in sorted(newdict)],
    #                   index=pd.MultiIndex.from_tuples([i for i in sorted(newdict.keys())]))
    marker_range = list(np.arange(
        int(sample / 10), sample, int(sample / 10)))

    for index, metric in enumerate(plt_metrics):
        metric_df = metrics[metric]
        print("Computing rolling %s." % metric)
        metric_df = compute_rolling_df_mean(metric_df, mean_smoothing)
        print("Normalizing %s." % metric)
        metric_df = normalize_df_min_max(metric_df)
        print ("Plotting %s..." % metric)
        if index == 0:
            plt_legend = "brief"
        else:
            plt_legend = False
        ax[index] = sns.lineplot(data=metric_df.sample(sample),
                                 ax=ax[index], legend=plt_legend,
                                 markers=True, markevery=marker_range)
        # markers=True, markersize=8)
        ax[index].set_ylabel(metric)
        if index == num_subplots - 1:
            ax[index].set_xlabel("Steps")
        ax[index].set_xlim([0, timesteps])
        ax[index].margins(y=0.15)
    # tcks = ax[num_subplots - 1].get_xticks()
    # tcks[-1] = timesteps
    # ax[num_subplots - 1].set_xticks(tcks)
    # fig.subplots_adjust(hspace=0.1, left=0.12, right=0.95)
    # _, handles = ax[num_subplots - 1].get_legend_handles_labels()
    ax[0].legend(bbox_to_anchor=(0.5, 1.45), loc="upper center",
                 fancybox=True, shadow=True, ncol=len(algos))
    print("Saving plot %s" % plt_name)
    check_plt_dir(plt_name)
    plt.savefig(plt_name + ".pdf", bbox_inches='tight', pad_inches=0.05)
    plt.savefig(plt_name + ".png", bbox_inches='tight', pad_inches=0.05)
    plt.gcf().clear()


def preprocess_data(algo, runs, transport_dir):
    run_list = {"rewards": [], "actions": [], "backlog": [],
                "bw_tx": [], "olimit": [], "drops": []}
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
            run_list["rewards"].append(rewards)
        num_samples = len(rewards)
        # actions
        print("Computing mean of host actions per step.")
        actions = host_actions.mean(axis=0)
        if actions.size:
            run_list["actions"].append(actions)
        # queues
        print("Computing mean of interface queues per step.")
        flat_queues = port_queues.mean(axis=0)
        if flat_queues.size:
            run_list["backlog"].append(flat_queues)
        # bandwidths
        print("Computing mean of interface bandwidth per step.")
        flat_bw = port_bws.mean(axis=0)
        if flat_bw.size:
            run_list["bw_tx"].append(flat_bw)
        # overlimits
        print("Computing mean of interface overlimits per step.")
        mean_overlimits = port_overlimits.mean(axis=0)
        if mean_overlimits.size:
            run_list["olimit"].append(mean_overlimits)
        # drops
        mean_drops = port_drops.mean(axis=0)
        print("Computing mean of interface drops per step.")
        if mean_drops.size:
            run_list["drops"].append(mean_drops)

    return run_list, num_samples


def plot(data_dir, plot_dir, name):
    test_config = parse_config(data_dir)
    rl_algos = test_config["rl_algorithms"]
    tcp_algos = test_config["tcp_algorithms"]
    algos = rl_algos + tcp_algos
    runs = test_config["runs"]
    timesteps = test_config["timesteps"]
    min_samples = timesteps
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
            run_list, num_samples, = preprocess_data(algo, runs, transport_dir)
            if (num_samples < min_samples):
                min_samples = num_samples
            # average over all runs
            print ("Computing the average across all runs.")
            for stat in run_list.keys():
                min_len = min([len(ls) for ls in run_list[stat]])
                pruned_list = [ls[:min_len] for ls in run_list[stat]]
                plt_stats[stat][algo] = np.mean(pruned_list, axis=0)
        plt_name = "%s/" % (plot_dir)
        plt_name += "%s" % name
        plt_name += "_%s" % topo
        plt_name += "_%s" % transport
        plt_name += "_%s" % timesteps
        plot_lineplot(algos, plt_stats, min_samples, plt_name)
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
