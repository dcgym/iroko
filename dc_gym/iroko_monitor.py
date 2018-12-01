import subprocess
import re
import multiprocessing

MAX_CAPACITY = 10e6   # Max capacity of link


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
                print("%s: Caught Interrupt..." % self.name)
                self.kill.set()
        print ("%s: Exiting..." % self.name)
        return

    def terminate(self):
        print("%s: Received termination signal" % self.name)
        self.kill.set()


class StatsCollector(Collector):

    def __init__(self, iface_list, shared_stats):
        Collector.__init__(self, iface_list)
        self.name = 'StatsCollector'
        self.stats = shared_stats
        self.init_stats()

    def init_stats(self):
        tmp_stats = {}
        tmp_stats["bws_rx"] = 0
        tmp_stats["bws_tx"] = 0
        tmp_stats["free_bandwidths"] = 0
        tmp_stats["drops"] = 0
        tmp_stats["overlimits"] = 0
        tmp_stats["queues"] = 0
        for iface in self.iface_list:
            self.stats[iface] = tmp_stats

    def _get_bandwidths(self, iface_list):
        # cmd3 = "ifstat -i %s -q 0.1 1 | awk '{if (NR==3) print $2}'" % (iface)
        # iface_string = ",".join(iface_list )
        processes = []
        for iface in iface_list:
            cmd = (" ifstat -i %s -b -q 0.5 1 | awk \'{if (NR==3) print $0}\' | \
                   awk \'{$1=$1}1\' OFS=\", \"" % (iface))  # | sed \'s/\(\([^,]*,\)\{1\}[^,]*\),/\1;/g\'
            # output = subprocess.check_output(cmd, shell=True)
            proc = subprocess.Popen([cmd], stdout=subprocess.PIPE,
                                    shell=True)
            processes.append((proc, iface))

        for proc, iface in processes:
            tmp_stats = self.stats[iface]
            proc.wait()
            output, _ = proc.communicate()
            output = output.decode()
            bw = output.split(',')
            try:
                tmp_stats["bws_rx"] = float(bw[0]) * 1000
                tmp_stats["bws_tx"] = float(bw[1]) * 1000
            except Exception as e:
                # print("Error Collecting Bandwidth: %s" % e)
                tmp_stats["bws_rx"] = 0
                tmp_stats["bws_tx"] = 0
                self.kill.set()
            self.stats[iface] = tmp_stats

    def _get_free_bw(self, capacity, speed):
        # freebw: Kbit/s
        return max(capacity - speed * 8 / 1000.0, 0)

    def _get_free_bandwidths(self, bandwidths):
        free_bandwidths = {}
        for iface, bandwidth in bandwidths.iteritems():
            free_bandwidths[iface] = self._get_free_bw(MAX_CAPACITY, bandwidth)
        return free_bandwidths

    def _get_qdisc_stats(self, iface_list):
        re_dropped = re.compile(r'(?<=dropped )[ 0-9]*')
        re_overlimit = re.compile(r'(?<=overlimits )[ 0-9]*')
        re_queued = re.compile(r'backlog\s[^\s]+\s([\d]+)p')
        for iface in iface_list:
            tmp_queues = self.stats[iface]
            cmd = "tc -s qdisc show dev %s" % (iface)
            # cmd1 = "tc -s qdisc show dev %s | grep -ohP -m1 '(?<=dropped )[ 0-9]*'" % (iface)
            drop_return = {}
            over_return = {}
            queue_return = {}
            try:
                output = subprocess.check_output(cmd.split()).decode()
                drop_return = re_dropped.findall(output)
                over_return = re_overlimit.findall(output)
                queue_return = re_queued.findall(output)
            except Exception as e:
                # print("Error Collecting Queues: %s" % e)
                drop_return[0] = 0
                over_return[0] = 0
                queue_return[0] = 0
                self.kill.set()
            tmp_queues["drops"] = int(drop_return[0])
            tmp_queues["overlimits"] = int(over_return[0])
            tmp_queues["queues"] = int(queue_return[0])
            self.stats[iface] = tmp_queues

    def _collect(self):
        self._get_bandwidths(self.iface_list)
        self._get_qdisc_stats(self.iface_list)


class FlowCollector(Collector):

    def __init__(self, iface_list, host_ips, src_flows, dst_flows):
        Collector.__init__(self, iface_list)
        self.name = 'FlowCollector'
        self.host_ips = host_ips
        self.src_flows = src_flows
        self.dst_flows = dst_flows
        self.init_flows()

    def init_flows(self):
        for iface in self.iface_list:
            self.src_flows[iface] = [0] * len(self.host_ips)
            self.dst_flows[iface] = [0] * len(self.host_ips)

    def _get_flow_stats(self, iface_list):
        processes = []
        for iface in iface_list:
            cmd = ("sudo timeout 1 tcpdump -l -i " + iface + " -n -c 20 ip 2>/dev/null | " +
                   "grep -P -o \'([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+).*? > ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)\' | " + "grep -P -o \'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+\' | xargs -n 2 echo | awk \'!a[$0]++\'")
            # output = subprocess.check_output(cmd, shell=True)
            proc = subprocess.Popen(
                [cmd], stdout=subprocess.PIPE, shell=True)
            processes.append((proc, iface))

        for proc, iface in processes:
            proc.wait()
            output, _ = proc.communicate()
            output = output.decode()
            src_flows = [0] * len(self.host_ips)
            dst_flows = [0] * len(self.host_ips)
            for row in output.split('\n'):
                if row != '':
                    src, dst = row.split(' ')
                    for i, ip in enumerate(self.host_ips):
                        if src == ip:
                            src_flows[i] = 1
                        if dst == ip:
                            dst_flows[i] = 1
            self.src_flows[iface] = src_flows
            self.dst_flows[iface] = dst_flows

    def _collect(self):
        self._get_flow_stats(self.iface_list)
