from math import fsum
import itertools
import json
import re
import os
import itertools  # noqa
import matplotlib
matplotlib.use('Agg')
import numpy as np
import matplotlib.pyplot as plt  # noqa
from monitor.helper import stdev
from monitor.helper import avg
from monitor.helper import read_list
from monitor.helper import cdf


class IrokoPlotter():

    def __init__(self, plt_dir, num_ifaces, epochs):
        self.name = 'IrokoPlotter'
        self.max_bw = 10                # Max capacity of link adjusted to mbit
        self.max_queue = 50             # Max queue per link
        self.num_ifaces = num_ifaces    # Num of monitored interfaces
        self.epochs = epochs            # Number of total epochs that are run
        self.plt_dir = plt_dir          # Directory of the plots
        # Check if the directory actually exists
        self.check_plt_dir(plt_dir)

    def check_plt_dir(self, plt_name):
        if not os.path.exists(plt_name):
            print("Folder %s does not exist! Creating..." % plt_name)
            plt_dir = os.path.dirname(plt_name)
            if plt_dir == '':
                os.makedirs(plt_name)
            else:
                os.makedirs(plt_dir)

    def moving_average(self, input_list, n=100):
        cumsum, moving_aves = [0], []
        for i, x in enumerate(input_list, 1):
            cumsum.append(cumsum[i - 1] + x)
            if i >= n:
                moving_ave = (cumsum[i] - cumsum[i - n]) / n
                # can do stuff with moving_ave here
                moving_aves.append(moving_ave)
        return moving_aves

    def evolving_average(self, input_list, n=100):
        avgreward = []
        summation = avg(input_list[:n - 1])
        i = n
        for r in input_list[n:]:
            summation += float(r)
            avgreward.append(summation / float(i))
            i += 1
        return avgreward

    def get_bw_stats(self, input_file, pat_iface):
        pat_iface = re.compile(pat_iface)
        data = read_list(input_file)

        rate = {}
        column = 3
        for row in (data):
            l_row = list(row)
            try:
                ifname = l_row[1]
            except Exception as e:
                break
            if pat_iface.match(ifname):
                if ifname not in rate:
                    rate[ifname] = []
                try:
                    rate[ifname].append(float(l_row[column]) * 8.0 / (1 << 20))
                except Exception as e:
                    break
        vals = {}
        avg_bw = []
        match = 0
        avg_bw_iface = {}
        filtered_bw = {}
        for iface, bws in rate.items():
            rate[iface] = self.moving_average(bws[10:-10], 100)
            avg_bw.append(avg(bws[10:-10]))
            avg_bw_iface[iface] = avg(bws[10:-10])
            match += 1
        # Update the num of interfaces to reflect true matches
        # TODO: This is a hack. Remove.
        self.num_ifaces = match
        total_bw = list(itertools.chain.from_iterable(rate.values()))
        vals["avg_bw_iface"] = avg_bw_iface
        vals["avg_bw"] = fsum(avg_bw)
        vals["median_bw"] = np.median(total_bw)
        vals["max_bw"] = max(total_bw)
        vals["stdev_bw"] = stdev(total_bw)
        return vals, rate

    def prune_bw(self, out_dir, switch):
        print("Pruning: %s:" % out_dir)
        input_file = out_dir + '/rate.txt'
        summary_file = out_dir + '/rate_summary.json'
        pruned_file = out_dir + '/rate_filtered.json'
        summaries, filtered_bw = self.get_bw_stats(input_file, switch)
        with open(pruned_file, 'w') as fp:
            json.dump(filtered_bw, fp)
            fp.close()
        with open(summary_file, 'w') as fp:
            json.dump(summaries, fp)
            fp.close()
        os.remove(input_file)

    def get_bw_dict(self, file):
        with open(file, 'r') as fp:
            data = json.load(fp)
            fp.close()
            return data

    def get_eff_bw_stats(self, input_file):
        data = read_list(input_file, " ")
        eff_bw = []
        for row in data:
            l_row = list(row)
            if l_row[0] != "host_stat:":
                continue

            ebw = 0

            try:
                ebw = float(l_row[-1])
            except:
                continue

            eff_bw.append(ebw)

        return eff_bw

    def get_qlen_stats(self, input_file, pat_iface):
        data = read_list(input_file)
        pat_iface = re.compile(pat_iface)
        qlen = {}
        for row in data:
            l_row = list(row)
            try:
                ifname = l_row[0]
            except Exception as e:
                break
            if pat_iface.match(ifname):
                if ifname not in qlen:
                    qlen[ifname] = []
                try:
                    qlen[ifname].append(int(l_row[2]))
                except Exception as e:
                    break
        vals = {}
        qlens = []
        avg_qlen_iface = {}
        full_qlen_iface = {}
        for iface, queues in qlen.items():
            qlens.append(queues)
            avg_qlen_iface[iface] = avg(queues)
            full_qlen_iface[iface] = queues

        # qlens = map(float, col(2, data))[10:-10]

        qlens = list(itertools.chain.from_iterable(qlens))
        vals["full_qlen_iface"] = full_qlen_iface
        vals["avg_qlen_iface"] = avg_qlen_iface
        vals["avg_qlen"] = avg(qlens)
        vals["median_qlen"] = np.median(qlens)
        vals["max_qlen"] = max(qlens)
        vals["stdev_qlen"] = stdev(qlens)
        vals["xcdf_qlen"], vals["ycdf_qlen"] = cdf(qlens)
        return vals

    def plot_test_bw(self, input_dir, plt_name, traffic_files, labels, algorithms):
        fbb = self.num_ifaces * self.max_bw
        num_plot = 2
        num_t = len(traffic_files)
        n_t = num_t / num_plot
        ind = np.arange(n_t)
        width = 0.15
        fig = plt.figure(1)
        fig.set_size_inches(8.5, 6.5)

        bb = {}
        for algo, conf in algorithms.items():
            bb[algo] = []
            for tf in traffic_files:
                print("algo:", tf)
                input_file = input_dir + \
                    '/%s/%s/rate_summary.json' % (conf['pre'], tf)
                results = self.get_bw_dict(input_file)
                avg_bw = float(results['avg_bw'])
                print(avg_bw)
                bb[algo].append(avg_bw / fbb / 2)
        for i in range(num_plot):
            fig.set_size_inches(24, 12)
            ax = fig.add_subplot(2, 1, i + 1)
            ax.yaxis.grid()
            plt.ylim(0.0, 1.0)
            plt.xlim(0, 10)
            plt.ylabel('Normalized Average Bisection Bandwidth')
            plt.xticks(ind + 2.5 * width, labels[i * n_t:(i + 1) * n_t])
            p_bar = []
            p_legend = []
            index = 0
            for algo, conf in algorithms.items():
                p = plt.bar(ind + (index + 1.5) * width, bb[algo][i * n_t:(i + 1) * n_t], width=width,
                            color=conf['color'])
                p_bar.append(p[0])
                p_legend.append(algo)
                index += 1
            plt.legend(p_bar, p_legend, loc='upper left')
            plt.savefig("%s/%s" % (self.plt_dir, plt_name))
        plt.grid(True)
        plt.gcf().clear()

    def plot_test_qlen(self, input_dir, plt_name, traffic_files, labels, algorithms, iface):
        fig = plt.figure(1)
        fig.set_size_inches(8.5, 6.5)
        for i, tf in enumerate(traffic_files):
            plt.grid(True)
            fig = plt.figure(1)
            fig.set_size_inches(40, 12)
            ax = fig.add_subplot(2, len(traffic_files) / 2, i + 1)
            ax.yaxis.grid()
            plt.ylim((0.8, 1.0))
            plt.ylabel("Fraction", fontsize=16)
            plt.xlabel(labels[i], fontsize=18)
            for algo, conf in algorithms.items():
                print("%s:%s" % (algo, tf))
                input_file = input_dir + '/%s/%s/qlen.txt' % (conf['pre'], tf)
                results = self.get_qlen_stats(input_file, conf['sw'])
                plt.plot(results['xcdf_qlen'], results['ycdf_qlen'],
                         label=labels[i], color=conf['color'], lw=2)
            plt.legend(bbox_to_anchor=(1.5, 1.22),
                       loc='upper right', fontsize='x-large')
            plt.savefig("%s/%s" % (self.plt_dir, plt_name))
        plt.gcf().clear()

    def plot_train_bw(self, input_dir, plt_name, traffic_files, algorithm):
        algo = algorithm[0]
        conf = algorithm[1]
        fbb = self.num_ifaces * self.max_bw
        # folders = glob.glob('%s/%s_*' % (input_dir, conf['pre']))
        bb = {}
        for tf in traffic_files:
            for e in range(self.epochs):
                bb['%s_%s' % (algo, e)] = []
                input_file = input_dir + \
                    '/%s_%d/%s/rate_summary.json' % (conf['pre'], e, tf)
                results = self.get_bw_dict(input_file)
                avg_bw = float(results['avg_bw'])
                print("%s %s Epoch %d: Avg BW %f" % (algo, tf, e, avg_bw))
                bb['%s_%s' % (algo, e)].append(avg_bw / fbb / 2)

            p_bar = []
            p_legend = []
            for i in range(self.epochs):
                p_bar.append(bb['%s_%d' % (algo, i)][0])
                p_legend.append('Epoch %i' % i)
            print("%s: Total Average Bandwidth: %f" % (tf, avg(p_bar)))
            plt.plot(p_bar)
            x_val = list(range(self.epochs + 1))
            if self.epochs > 100:
                x_step = x_val[0::(self.epochs / 10)]
                plt.xticks(x_step)
            plt.xlabel('Epoch')
            plt.ylabel('Normalized Average Bisection Bandwidth')
            axes = plt.gca()
            axes.set_ylim([-0.1, 1.1])
            plt.savefig("%s/%s_%s" % (self.plt_dir, plt_name, tf))
            plt.gcf().clear()

    def plot_train_bw_avg(self, input_dir, plt_name, traffic_files, algorithm):
        algo = algorithm[0]
        conf = algorithm[1]
        # folders = glob.glob('%s/%s_*' % (input_dir, conf['pre']))
        for tf in traffic_files:
            print("Average BW: %s: %s" % (algo, tf))
            bb = {}
            for e in range(self.epochs):
                input_file = input_dir + \
                    '/%s_%d/%s/rate_filtered.json' % (conf['pre'], e, tf)
                results = self.get_bw_dict(input_file)
                for iface, bw_list in results.items():
                    if iface not in bb:
                        bb[iface] = []
                    else:
                        bb[iface].extend(bw_list)

            for iface, bws in bb.items():
                plt.plot(self.evolving_average(bws, 1000), label=iface)
            plt.xlabel('Iterations')
            plt.ylabel('Average Interface Bisection Bandwidth')
            plt.legend(loc='center right')
            plt.savefig("%s/%s_%s" % (self.plt_dir, plt_name, tf))
            plt.gcf().clear()

    def plot_train_bw_iface(self, input_dir, plt_name, traffic_files, algorithm):
        algo = algorithm[0]
        conf = algorithm[1]
        fbb = self.max_bw
        # folders = glob.glob('%s/%s_*' % (input_dir, conf['pre']))
        bb = {}
        for tf in traffic_files:
            for epoch in range(self.epochs):
                bb['%s_%s' % (algo, epoch)] = {}
                input_file = input_dir + \
                    '/%s_%d/%s/rate_summary.json' % (conf['pre'], epoch, tf)
                results = self.get_bw_dict(input_file)
                avg_bw = results['avg_bw_iface']
                print("Average BW %s %s Epoch %d" % (algo, tf, epoch))
                print(avg_bw)
                for iface, bw in avg_bw.items():
                    bb['%s_%s' % (algo, epoch)].setdefault(
                        iface, []).append(float(bw) / fbb)
            for iface, bw in bb['%s_%s' % (algo, 0)].items():
                p_bar = []
                p_legend = []
                for i in range(self.epochs):
                    p_bar.append(bb['%s_%d' % (algo, i)][iface][0])
                    p_legend.append('Epoch %i' % i)
                print("Interface %s: Total Average Bandwidth: %f" %
                      (iface, avg(p_bar)))
                plt.plot(p_bar, label=iface)
            x_val = list(range(self.epochs + 1))
            if self.epochs > 100:
                x_step = x_val[0::(self.epochs / 10)]
                plt.xticks(x_step)
            plt.xlabel('Epoch')
            plt.ylabel('Normalized Average Bisection Bandwidth')
            axes = plt.gca()
            axes.set_ylim([-0.1, 1.1])
            plt.legend(loc='center right')
            plt.savefig("%s/%s_%s" % (self.plt_dir, plt_name, tf))
            plt.gcf().clear()

    def plot_effective_bw(self, input_dir, plt_name, traffic_files, algorithm):
        algo = algorithm[0]
        conf = algorithm[1]
        # folders = glob.glob('%s/%s_*' % (input_dir, conf['pre']))
        bb = {}
        hosts = ["h1", "h2", "h3", "h4"]
        for tf in traffic_files:
            for epoch in range(self.epochs):
                bb['%s_%s' % (algo, epoch)] = {}
                for host in hosts:
                    input_file = input_dir + \
                        '/%s_%d/%s/%s.out' % (conf['pre'], epoch, tf, host)
                    eff_bw_stat = self.get_eff_bw_stats(input_file)
                    avg_eff_bw = np.median(eff_bw_stat)
                    print("Effective Bandwidth Average: %s %s Epoch %d" %
                          (algo, tf, epoch))
                    print(avg_eff_bw)
                    bb['%s_%s' % (algo, epoch)][host] = avg_eff_bw

            for host, avg_eff_bw in bb['%s_%s' % (algo, 0)].items():
                p_bar = []
                p_legend = []
                for i in range(self.epochs):
                    p_bar.append(bb['%s_%d' % (algo, i)][host])
                    p_legend.append('Epoch %i' % i)
                print("Host %s: Total Average Effective Bandwidth: %f" %
                      (host, avg(p_bar)))
                plt.plot(p_bar, label=host)
            x_val = list(range(self.epochs + 1))
            if self.epochs > 100:
                x_step = x_val[0::(self.epochs / 10)]
                plt.xticks(x_step)
            plt.xlabel('Epoch')
            plt.ylabel('Average Effective Bandwidth (bytes/sec)')
            axes = plt.gca()
            # axes.set_ylim([0, self.max_queue])
            plt.legend(loc='center right')
            plt.savefig("%s/%s_%s" % (self.plt_dir, plt_name, tf))
            plt.gcf().clear()

    def plot_train_qlen(self, input_dir, plt_name, traffic_files, algorithm):
        algo = algorithm[0]
        conf = algorithm[1]
        # folders = glob.glob('%s/%s_*' % (input_dir, conf['pre']))
        bb = {}
        for tf in traffic_files:
            for e in range(self.epochs):
                bb['%s_%s' % (algo, e)] = []
                input_file = input_dir + \
                    '/%s_%d/%s/qlen.txt' % (conf['pre'], e, tf)
                results = self.get_qlen_stats(input_file, conf['sw'])
                avg_qlen = float(results['avg_qlen'])
                print("%s %s Epoch %d: Avg Qlen %f" % (algo, tf, e, avg_qlen))
                bb['%s_%s' % (algo, e)].append(avg_qlen)

            p_bar = []
            p_legend = []
            for i in range(self.epochs):
                p_bar.append(bb['%s_%d' % (algo, i)][0])
                p_legend.append('Epoch %i' % i)
            print("%s: Total Average Qlen: %f" % (tf, avg(p_bar)))
            plt.plot(p_bar)
            x_val = list(range(self.epochs + 1))
            if self.epochs > 100:
                x_step = x_val[0::(self.epochs / 10)]
                plt.xticks(x_step)
            plt.xlabel('Epoch')
            plt.ylabel('Average Queue Length')
            axes = plt.gca()
            axes.set_ylim([0, self.max_queue])
            plt.savefig("%s/%s_%s" % (self.plt_dir, plt_name, tf))
            plt.gcf().clear()

    def plot_train_qlen_avg(self, input_dir, plt_name, traffic_files, algorithm):
        algo = algorithm[0]
        conf = algorithm[1]
        # folders = glob.glob('%s/%s_*' % (input_dir, conf['pre']))
        for tf in traffic_files:
            print("Qlen Evolving Average: %s: %s" % (algo, tf))
            bb = {}
            for e in range(self.epochs):
                input_file = input_dir + \
                    '/%s_%d/%s/qlen.txt' % (conf['pre'], e, tf)
                results = self.get_qlen_stats(input_file, conf['sw'])
                full_qlens = results["full_qlen_iface"]
                for iface, qlen_list in full_qlens.items():
                    if iface not in bb:
                        bb[iface] = []
                    else:
                        bb[iface].extend(qlen_list)
            for iface, qlens in bb.items():
                plt.plot(self.evolving_average(qlens, 100), label=iface)
            plt.xlabel('Iterations')
            plt.ylabel('Average Interface Queue Length')
            plt.legend(loc='center left')
            plt.savefig("%s/%s_%s" % (self.plt_dir, plt_name, tf))
            plt.gcf().clear()

    def plot_train_qlen_iface(self, input_dir, plt_name, traffic_files, algorithm):
        algo = algorithm[0]
        conf = algorithm[1]
        # folders = glob.glob('%s/%s_*' % (input_dir, conf['pre']))
        bb = {}
        for tf in traffic_files:
            for epoch in range(self.epochs):
                bb['%s_%s' % (algo, epoch)] = {}
                input_file = input_dir + \
                    '/%s_%d/%s/qlen.txt' % (conf['pre'], epoch, tf)
                results = self.get_qlen_stats(input_file, conf['sw'])
                avg_qlen = results["avg_qlen_iface"]
                print("Qlen Average: %s %s Epoch %d" % (algo, tf, epoch))
                print(avg_qlen)
                for iface, qlen in avg_qlen.items():
                    bb['%s_%s' % (algo, epoch)].setdefault(
                        iface, []).append(float(qlen))

            for iface, bw in bb['%s_%s' % (algo, 0)].items():
                p_bar = []
                p_legend = []
                for i in range(self.epochs):
                    p_bar.append(bb['%s_%d' % (algo, i)][iface][0])
                    p_legend.append('Epoch %i' % i)
                print("Interface %s: Total Average Qlen: %f" %
                      (iface, avg(p_bar)))
                plt.plot(p_bar, label=iface)
            x_val = list(range(self.epochs + 1))
            if self.epochs > 100:
                x_step = x_val[0::(self.epochs / 10)]
                plt.xticks(x_step)
            plt.xlabel('Epoch')
            plt.ylabel('Average Queue Length')
            axes = plt.gca()
            # axes.set_ylim([0, self.max_queue])
            plt.legend(loc='center right')
            plt.savefig("%s/%s_%s" % (self.plt_dir, plt_name, tf))
            plt.gcf().clear()

    def plot_reward(self, fname, plt_name):
        float_rewards = []
        with open(fname) as f:
            str_rewards = f.readlines()
        str_rewards = [x.strip() for x in str_rewards]
        for reward in str_rewards:
            float_rewards.append(float(reward))
        plt.plot(float_rewards)
        plt.ylabel('Reward')
        plt.savefig(plt_name)
        plt.savefig("%s/%s" % (self.plt_dir, plt_name))
        plt.gcf().clear()

    def plot_avgreward(self, fname, plt_name):
        with open(fname) as f:
            content = f.readlines()
        # you may also want to remove whitespace characters like `\n` at the end of each line
        content = [float(x.strip()) for x in content]
        window = 1000
        reward_mean = self.moving_average(content, window)
        reward_evolve = self.evolving_average(content, window)

        plt.subplot(2, 1, 1)
        plt.plot(reward_mean, label="Mean %d" % window)
        plt.legend(loc='upper center')
        plt.ylabel('Reward')
        plt.subplot(2, 1, 2)
        plt.plot(reward_evolve, label="Evolution")
        plt.ylabel('Reward')
        plt.xlabel('Iterations')
        plt.legend(loc='center right')
        plt.savefig("%s/%s" % (self.plt_dir, plt_name))
        plt.gcf().clear()

    def plot_results(self, traffic_files, algo, conf):
        self.plot_avgreward(
            "reward.txt", "avgreward_%s_%s" % (algo, self.epochs))
        self.plot_train_bw('results', '%s_train_bw' %
                           algo, traffic_files, (algo, conf))
        self.plot_train_bw_iface(
            'results', '%s_env_bw_alt' % algo, traffic_files, (algo, conf))
        self.plot_train_bw_avg(
            'results', '%s_env_bw_avg' % algo, traffic_files, (algo, conf))
        self.plot_train_qlen(
            'results', '%s_env_qlen' % algo, traffic_files, (algo, conf))
        self.plot_train_qlen_iface(
            'results', '%s_env_qlen_alt' % algo, traffic_files, (algo, conf))
        self.plot_train_qlen_avg(
            'results', '%s_env_qlen_avg' % algo, traffic_files, (algo, conf))
        self.plot_effective_bw(
            'results', '%s_env_effective_bw' % algo, traffic_files, (algo, conf))
