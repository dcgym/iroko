from __future__ import division  # For Python 2
import os
import fnmatch
import json
import csv
import argparse
import math
import shelve
import numpy as np
import pandas as pd
import dc_gym.utils as dc_utils

# configure logging
import logging
log = logging.getLogger(__name__)

PLOT_DIR = os.path.dirname(os.path.abspath(__file__)) + "/plots"
ROOT = "candidates"

PARSER = argparse.ArgumentParser()
PARSER.add_argument('--input', '-i', dest='input_dir')
ARGS = PARSER.parse_args()


def parse_config(conf_dir, name):
    with open(f"{conf_dir}/{name}.json") as conf_file:
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
    pd_frame = pd.DataFrame({k: pd.Series(v) for k, v in np_dict[key].items()})
    return pd_frame.astype(df_type)


def plot_barchart(algos, plt_stats, plt_name):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

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
    ax_overlimits.bar(range(len(bar_labels)),
                      bar_overlimits,
                      tick_label=bar_labels)
    ax_drops.bar(range(len(bar_labels)), bar_drops, tick_label=bar_labels)
    plt.savefig(plt_name + "_bar.pdf")
    plt.savefig(plt_name + "_bar.png")
    plt.gcf().clear()


def strided_app(a, L, S):
    # Window len = L, Stride len/stepsize = S
    nrows = ((a.size - L) // S) + 1
    n = a.strides[0]
    return np.lib.stride_tricks.as_strided(a,
                                           shape=(nrows, L),
                                           strides=(S * n, n))


def compute_rolling_df_mean(pd_df, roll):
    rolling_df = pd_df.rolling(roll).mean().dropna()
    return rolling_df.reset_index(drop=True)


def compute_rolling_df_99p(pd_df, roll):
    log.info(roll)
    rolling_df = pd_df.rolling(roll, center=True).quantile(.01).dropna()
    log.info(rolling_df)
    return rolling_df.reset_index(drop=True)


def normalize_df_min_max(pd_df):
    df_max = np.nanmax(pd_df.values)
    df_min = np.nanmin(pd_df.values)
    normalized_df = (pd_df - df_min) / (df_max - df_min)
    return normalized_df


def normalize_df_min_max_range(pd_df, df_min, df_max):
    normalized_df = (pd_df - df_min) / (df_max - df_min)
    return normalized_df


def normalize_df_tanh(pd_df, df_min, df_max):
    df_mean = np.mean(pd_df.values)
    df_std = np.std(pd_df.values)
    normalized_df = np.tanh(0.01 (pd_df - df_mean) / df_std + 1)
    return normalized_df


def normalize_df_z_score(pd_df):
    df_mean = np.nanmean(pd_df.values)
    df_std = np.nanstd(pd_df.values)
    normalized_df = (pd_df - df_mean) / df_std
    return normalized_df


def plot_lineplot(algos, plt_stats, num_samples, plt_name):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn as sns

    # Set seaborn style for plotting
    sns.set(style="ticks",
            rc={
                "lines.linewidth": 1.2,
                "axes.spines.right": False,
                "axes.spines.top": False,
                'lines.markeredgewidth': 0.1,
            })
    # sns.set_context("paper")
    metrics = {}
    plt_metrics = ["reward", "queues", "bw"]
    log.info("Converting numpy arrays into pandas dataframes.")
    metrics["reward"] = np_dict_to_pd(plt_stats, "rewards")
    metrics["actions"] = np_dict_to_pd(plt_stats, "actions")
    metrics["queues"] = np_dict_to_pd(plt_stats, "backlog")
    metrics["bw"] = np_dict_to_pd(plt_stats, "bw_tx")
    log.info("Computing overlimit deltas.")
    metrics["overlimits"] = np_dict_to_pd(plt_stats, "olimit").diff()
    log.info("Computing drops deltas.")
    metrics["drops"] = np_dict_to_pd(plt_stats, "drops").diff()

    fig, ax = plt.subplots(len(plt_metrics), 1, sharex=True, squeeze=True)
    mean_smoothing = math.ceil(num_samples / 100)
    if num_samples > 10000:
        sample = 10000
    else:
        sample = num_samples
    num_subplots = len(ax)
    marker_range = list(
        np.arange(math.ceil(sample / 10), sample, math.ceil(sample / 10)))
    for index, metric in enumerate(plt_metrics):
        metric_df = metrics[metric]
        log.info("Drop overlimit rows %s.", metric)
        metric_df = metric_df.drop(metric_df.index[num_samples:])
        log.info("Computing rolling %s.", metric)
        metric_df = compute_rolling_df_mean(metric_df, mean_smoothing)
        log.info("Normalizing %s.", metric)
        metric_df = normalize_df_min_max(metric_df)
        log.info("Plotting %s...", metric)
        if index == 0:
            plt_legend = "brief"
        else:
            plt_legend = False
        ax[index] = sns.lineplot(data=metric_df,
                                 ax=ax[index],
                                 legend=plt_legend,
                                 markers=True,
                                 markevery=marker_range)
        ax[index].set_ylabel(metric)
        if index == num_subplots - 1:
            ax[index].set_xlabel("Time")
        ax[index].set_xlim([0, num_samples])
        ax[index].margins(y=0.15)
    ax[0].legend(bbox_to_anchor=(0.5, 1.45),
                 loc="upper center",
                 fancybox=True,
                 shadow=True,
                 ncol=len(algos))
    log.info("Saving plot %s", plt_name)
    plt.savefig(plt_name + ".pdf", bbox_inches='tight', pad_inches=0.05)
    plt.savefig(plt_name + ".png", bbox_inches='tight', pad_inches=0.05)
    plt.gcf().clear()


def run_tcptrace(algo_dir):
    cmd = "tcptrace -lr --csv %s/*.pcap*" % algo_dir
    cmd += "| sed '/^#/ d' "
    cmd += "| sed -r '/^\\s*$/d' "
    cmd += "> %s/rtt.csv " % algo_dir
    os.system(cmd)


def process_rtt_files(data_dir, runs, algo):
    total_rtt = {
        "max": 0,
        "avg": 0,
        "stdev": 0,
    }
    for index in range(runs):
        row_rtt = {metric: [] for metric in total_rtt.keys()}
        run_dir = "%s/tcp_run%d" % (data_dir, index)
        results_folder = '%s/%s' % (run_dir, algo.lower())
        run_tcptrace(results_folder)
        rtt_name = "%s/rtt.csv" % results_folder
        log.info("Import csv file: %s", rtt_name)
        with open(rtt_name) as rtt_file:
            rtt_csv = csv.DictReader(rtt_file)
            for row in rtt_csv:
                for key, value in row.items():
                    for metric in total_rtt.keys():
                        if "last" not in key:
                            if key.startswith("RTT_%s" % metric):
                                row_rtt[metric].append(float(value))
    for metric in total_rtt.keys():
        total_rtt[metric] = np.nanmean(row_rtt[metric])
    return total_rtt


def analyze_pcap(rl_algos, tcp_algos, plt_name, runs, data_dir):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn as sns

    algos = rl_algos + tcp_algos
    host_rtt = {}
    for algo in algos:
        host_rtt[algo] = process_rtt_files(data_dir, runs, algo)
    pcap_df = pd.DataFrame.from_dict(host_rtt, orient='index')
    pcap_df = pd.melt(pcap_df.reset_index(),
                      id_vars='index',
                      var_name="Metric",
                      value_name="Average RTT (ms)")
    pcap_df = pcap_df.rename(columns={'index': 'Algorithm'})
    # Convert to milliseconds
    # pcap_df = pcap_df.div(1e6)
    fig = sns.catplot(x='Metric',
                      y='Average RTT (ms)',
                      hue="Algorithm",
                      data=pcap_df,
                      kind='bar')
    from itertools import cycle
    hatches = cycle(["/", "-", "+", "x", '-', '+', 'x', 'O', '.'])

    num_locations = len(pcap_df.Metric.unique())
    for i, patch in enumerate(fig.ax.patches):
        # Blue bars first, then green bars
        if i % num_locations == 0:
            hatch = next(hatches)
        patch.set_hatch(hatch)
    plt_name += "_rtt"
    log.info("Saving plot %s", plt_name)
    plt.savefig(plt_name + ".png", bbox_inches='tight', pad_inches=0.05)
    plt.savefig(plt_name + ".pdf", bbox_inches='tight', pad_inches=0.05)
    plt.gcf().clear()


def find_stats_files(results_folder, name):
    results = []
    for root, dirnames, filenames in os.walk(results_folder):
        for filename in fnmatch.filter(filenames, f"{name}.npy"):

            results.append(os.path.join(root, filename))
    return results


def get_stats(statistics, stats_dict, metrics):
    stats = {}
    rewards = np.array(statistics["reward"])
    num_samples = statistics["num_samples"]
    host_actions = np.moveaxis(statistics["actions"], 0, -1)
    port_stats = np.moveaxis(statistics["stats"], 0, -1)
    port_queues = np.array(port_stats[stats_dict["backlog"]])
    port_bws = np.array(port_stats[stats_dict["bw_tx"]])
    port_overlimits = np.array(port_stats[stats_dict["olimit"]])
    port_drops = np.array(port_stats[stats_dict["drops"]])
    # rewards
    if rewards.size:
        stats["rewards"] = rewards
    # actions
    log.info("Computing mean of host actions per step.")
    actions = host_actions.mean(axis=0)
    if actions.size:
        stats["actions"] = actions
    # queues
    log.info("Computing mean of interface queues per step.")
    flat_queues = port_queues.mean(axis=0)
    if flat_queues.size:
        stats["backlog"] = flat_queues
    # bandwidths
    log.info("Computing mean of interface bandwidth per step.")
    flat_bw = port_bws.mean(axis=0)
    if flat_bw.size:
        stats["bw_tx"] = flat_bw
    # overlimits
    log.info("Computing mean of interface overlimits per step.")
    mean_overlimits = port_overlimits.mean(axis=0)
    if mean_overlimits.size:
        stats["olimit"] = mean_overlimits
    # drops
    log.info("Computing mean of interface drops per step.")
    mean_drops = port_drops.mean(axis=0)
    if mean_drops.size:
        stats["drops"] = mean_drops
    return stats, num_samples


def merge_stats(stats):
    stats_avg = {}
    for metric in stats:
        zipped_metrics = list(map(list, zip(*stats[metric])))
        stats_avg[metric] = np.mean(zipped_metrics, axis=1)
    return stats_avg


def preprocess_data(algo, metrics, runs, transport_dir):
    run_list = {metric: [] for metric in metrics}
    samples = []
    for index in range(runs):
        run_dir = transport_dir + "run%d" % index
        results_folder = '%s/%s' % (run_dir, algo.lower())
        env_config = parse_config(results_folder, "env_config")
        stats_dict = env_config["stats_dict"]
        stats_files = find_stats_files(results_folder, "statistics")
        stats = {metric: [] for metric in metrics}
        for stats_file in stats_files:
            if not stats_file:
                log.info("No stats file found!")
                exit(1)
            log.info("Loading %s...", stats_file)
            try:
                statistics = shelve.open(stats_file)
                # statistics = np.load(stats_file, allow_pickle=True).item()
            except Exception as e:
                log.info("Error loading file %s:\n%s", stats_file, e)
                exit(1)
            stats_list, n_samples = get_stats(statistics, stats_dict, metrics)
            samples.append(n_samples)
            for metric in metrics:
                stats[metric].append(stats_list[metric])
        stats_avg = merge_stats(stats)
        for metric in metrics:
            run_list[metric].append(stats_avg[metric])
    return run_list, min(samples)


def plot(data_dir, plot_dir, name):
    test_config = parse_config(data_dir, "bench_config")
    rl_algos = test_config["rl_algorithms"]
    tcp_algos = test_config["tcp_algorithms"]
    algos = rl_algos + tcp_algos
    runs = test_config["runs"]
    episodes = test_config["episodes"]
    transports = test_config["transport"]
    topo = test_config["topology"]
    min_samples = np.inf
    for transport in transports:
        plt_name = "%s/" % (plot_dir)
        plt_name += "%s" % name
        dc_utils.check_dir(plt_name)
        plt_name += "/%s" % topo
        plt_name += "_%s" % transport
        plt_name += "_%se" % episodes
        plt_stats = {
            "rewards": {},
            "actions": {},
            "backlog": {},
            "bw_tx": {},
            "olimit": {},
            "drops": {}
        }
        for algo in algos:
            if algo in tcp_algos:
                transport_dir = data_dir + "/tcp_"
            else:
                transport_dir = data_dir + "/%s_" % (transport.lower())
            run_list, num_samples, = preprocess_data(algo, plt_stats.keys(),
                                                     runs, transport_dir)
            # replace the assumed sample number with actual observed samples
            if num_samples < min_samples:
                min_samples = num_samples
            # average over all runs
            log.info("Computing the average across all runs.")
            for stat in run_list.keys():
                min_len = min([len(ls) for ls in run_list[stat]])
                pruned_list = [ls[:min_len] for ls in run_list[stat]]
                plt_stats[stat][algo] = np.mean(pruned_list, axis=0)
        plot_lineplot(algos, plt_stats, min_samples, plt_name)
        # if transport == "tcp":
        #    analyze_pcap(rl_algos, tcp_algos, plt_name, runs, data_dir)
        # plot_barchart(algos, plt_stats, plt_name)


if __name__ == '__main__':
    logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)
    if ARGS.input_dir:
        plot(ARGS.input_dir, PLOT_DIR,
             os.path.basename(os.path.normpath(ARGS.input_dir)))
        exit(0)

    for folder in next(os.walk(ROOT))[1]:
        log.info("Crawling folder %s ", folder)
        machinedir = ROOT + "/" + folder
        plot(machinedir, PLOT_DIR, folder)
