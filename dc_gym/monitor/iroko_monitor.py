import subprocess
import multiprocessing
import ctypes
import os
import time
from dc_gym.utils import IrokoLogger
log = IrokoLogger("iroko")

FILE_DIR = os.path.dirname(os.path.abspath(__file__))


class Collector(multiprocessing.Process):

    def __init__(self, iface_list):
        multiprocessing.Process.__init__(self)
        self.name = 'Collector'
        self.iface_list = iface_list
        self.kill = multiprocessing.Event()

    def set_interfaces(self):
        cmd = "sudo ovs-vsctl list-br | xargs -L1 sudo ovs-vsctl list-ports"
        output = subprocess.check_output(cmd, shell=True).decode()
        iface_list_temp = []
        for row in output.split('\n'):
            if row != '':
                iface_list_temp.append(row)
        self.iface_list = iface_list_temp

    def run(self):
        while not self.kill.is_set():
            try:
                self._collect()
            except KeyboardInterrupt:
                log.error("%s: Caught Interrupt! Exiting..." % self.name)
                self.kill.set()
        self._clean()

    def _collect(self):
        raise NotImplementedError("Method _collect not implemented!")

    def terminate(self):
        log.info("%s: Received termination signal! Exiting.." % self.name)
        self.kill.set()

    def _clean(self):
        pass


class BandwidthCollector(Collector):

    def __init__(self, iface_list, shared_stats, stats_dict, max_bps):
        Collector.__init__(self, iface_list)
        self.name = 'StatsCollector'
        self.stats = shared_stats
        self.max_bps = max_bps
        self.stats_dict = stats_dict
        self.stats_offset = len(stats_dict)

    def _get_bandwidths(self, iface_list):

        processes = []
        for iface in iface_list:
            cmd = (" ifstat -i %s -b -q 0.5 1 | awk \'{if (NR==3) print $0}\' | \
                   awk \'{$1=$1}1\' OFS=\", \"" % (iface))
            proc = subprocess.Popen([cmd], stdout=subprocess.PIPE,
                                    shell=True)
            processes.append((proc, iface))

        for index, (proc, iface) in enumerate(processes):
            proc.wait()
            output, _ = proc.communicate()
            output = output.decode()
            bw = output.split(',')
            if bw[0] != 'n/a' and bw[1] != ' n/a\n':
                bps_rx = float(bw[0]) * 1000.0 / float(self.max_bps)
                bps_tx = float(bw[1]) * 1000.0 / float(self.max_bps)
                self.stats[self.stats_dict["bw_rx"]][index] = bps_rx
                self.stats[self.stats_dict["bw_tx"]][index] = bps_tx

    def _collect(self):
        self._get_bandwidths(self.iface_list)


class Qdisc(ctypes.Structure):
    pass


class QueueCollector(Collector):

    def __init__(self, iface_list, shared_stats, stats_dict, max_queue):
        Collector.__init__(self, iface_list)
        self.name = 'QueueCollector'
        self.stats = shared_stats
        self.stats_dict = stats_dict
        self.max_queue = max_queue
        self.stats_offset = len(stats_dict)
        self.q_lib = self._init_stats()

    def _init_stats(self):
        # init qdisc C library
        q_lib = ctypes.CDLL(FILE_DIR + '/libqdisc_stats.so')
        q_lib.init_qdisc_monitor.argtypes = [ctypes.c_char_p]
        q_lib.init_qdisc_monitor.restype = ctypes.POINTER(Qdisc)
        return q_lib

    # def _init_qdiscs(self, iface_list, q_lib):
    #     self.qdisc_map = {}
    #     for iface in iface_list:
    #         qdisc = q_lib.init_qdisc_monitor(iface)
    #         self.qdisc_map[iface] = qdisc

    # def _clean(self):
    #     for iface in self.iface_list:
    #         qdisc = self.qdisc_map[iface]
    #         self.q_lib.delete_qdisc_monitor(qdisc)

    def _get_qdisc_stats(self, iface_list):
        for index, iface in enumerate(iface_list):
            qdisc = self.q_lib.init_qdisc_monitor(iface.encode('ascii'))
            queue_backlog = float(self.q_lib.get_qdisc_backlog(qdisc))
            queue_backlog /= float(self.max_queue)
            queue_drops = self.q_lib.get_qdisc_drops(qdisc)
            queue_overlimits = self.q_lib.get_qdisc_overlimits(qdisc)
            # queue_rate_bps = self.q_lib.get_qdisc_rate_bps(qdisc)
            # queue_rate_pps = self.q_lib.get_qdisc_rate_pps(qdisc)
            self.stats[self.stats_dict["backlog"]][index] = queue_backlog
            self.stats[self.stats_dict["olimit"]][index] = queue_overlimits
            self.stats[self.stats_dict["drops"]][index] = queue_drops
            # # tx rate
            # self.stats[index][self.stats_dict["rate_bps"]] = queue_rate_bps
            # # packet rate
            # self.stats[index][self.stats_dict["rate_pps"]] = queue_rate_pps
            self.q_lib.delete_qdisc_monitor(qdisc)

    def _collect(self):
        self._get_qdisc_stats(self.iface_list)
        # We are too fast, let it rest for a bit...
        time.sleep(0.001)


class FlowCollector(Collector):

    def __init__(self, iface_list, host_ips, shared_flows):
        Collector.__init__(self, iface_list)
        self.name = 'FlowCollector'
        self.host_ips = host_ips
        self.shared_flows = shared_flows

    def _get_flow_stats(self, iface_list):
        processes = []
        for iface in iface_list:
            cmd = "sudo timeout 1 tcpdump -l -i %s " % iface
            cmd += "-n -c 50 ip 2>/dev/null | "
            cmd += "grep -P -o \'([0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+).*? > "
            cmd += "([0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+)\' | "
            cmd += "grep -P -o \'[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+\' | "
            cmd += "xargs -n 2 echo | awk \'!a[$0]++\'"
            # output = subprocess.check_output(cmd, shell=True)
            proc = subprocess.Popen(
                [cmd], stdout=subprocess.PIPE, shell=True)
            processes.append((proc, iface))
        for index, (proc, iface) in enumerate(processes):
            proc.wait()
            output, _ = proc.communicate()
            output = output.decode()
            for row in output.split('\n'):
                if row != '':
                    src, dst = row.split(' ')
                    for i, ip in enumerate(self.host_ips):
                        i_src = 0
                        i_dst = 1
                        self.shared_flows[index][i_src][i] = 0
                        self.shared_flows[index][i_dst][i] = 0
                        if src == ip:
                            self.shared_flows[index][i_src][i] = 1
                        if dst == ip:
                            self.shared_flows[index][i_dst][i] = 1

    def _collect(self):
        self._get_flow_stats(self.iface_list)
