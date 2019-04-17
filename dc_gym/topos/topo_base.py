import os
import sys
import random
import string

from mininet.node import RemoteController
from mininet.net import Mininet
from mininet.log import setLogLevel
from mininet.node import CPULimitedHost
from mininet.util import custom
from dc_gym.utils import *
log = IrokoLogger("iroko")

cwd = os.getcwd()
FILE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, FILE_DIR)

DEFAULT_CONF = {
    "max_capacity": 10e6,       # max bw capacity of link in bytes
    "min_capacity": 0.1e6,      # min possible bw of an interface in bytes
    "parallel_envs": False,     # enable ids to support multiple topologies
    "tcp_policy": "tcp"
}


class BaseTopo:

    def __init__(self, conf={}):
        self.conf = DEFAULT_CONF
        self.conf.update(conf)
        self.name = "base"
        self.topo = None
        self.started = False
        self.host_ctrl_map = {}
        self.net = None
        self.max_queue = 0
        self.max_bps = self.conf["max_capacity"]
        self.switch_id = self._generate_switch_id(self.conf)
        self.max_queue = self._calculate_max_queue(self.max_bps)
        self.prev_cc = self._get_active_congestion_control()
        self._set_congestion_control(self.conf)

    def _calculate_max_queue(self, max_bps):
        queue = 4e6
        if max_bps < 1e9:
            queue = 4e6 / (1e9 / max_bps)
            # keep a sensible minimum size
            if queue < 4e5:
                queue = 4e5
        return queue

    def _generate_switch_id(self, conf):
        ''' Mininet needs unique ids if we want to launch
         multiple topologies at once '''
        if not conf["parallel_envs"]:
            return ""
        # Best collision-free technique for the limited amount of characters
        sw_id = ''.join(random.choice(''.join([random.choice(
                string.ascii_letters + string.digits)
            for ch in range(4)])) for _ in range(4))
        return sw_id

    def _get_active_congestion_control(self):
        prev_cc = os.popen("sysctl -n net.ipv4.tcp_congestion_control").read()
        return prev_cc

    def _set_congestion_control(self, conf):
        if conf["tcp_policy"] == "dctcp":
            start_process("modprobe tcp_dctcp")
            start_process("sysctl -w net.ipv4.tcp_ecn=1")
        elif conf["tcp_policy"] == "tcp_nv":
            start_process("modprobe tcp_nv")
        elif conf["tcp_policy"] == "pcc":
            if (os.popen("lsmod | grep pcc").read() == ""):
                start_process("insmod %s/tcp_pcc.ko" % FILE_DIR)

    def _set_host_ip(self, net, topo):
        raise NotImplementedError("Method _set_host_ip not implemented!")

    def _connect_controller(self, controller):
        for i, host in enumerate(self.topo.hostlist):
            # Configure host
            self.net.addLink(controller, host)
            # Configure controller
            ctrl_iface = "%sc0-eth%d" % (self.switch_id, i)

            for index, switch in self.topo.ports[host].items():
                switch_iface = switch[0] + "-eth" + str(switch[1])
                self.host_ctrl_map[switch_iface] = ctrl_iface

    def _config_topo(self, ovs_v, is_ecmp):
        raise NotImplementedError("Method _config_topo not implemented!")

    def _calc_ecn(self, max_throughput, avg_pkt_size):
        # Calculate the marking threshold as part of the BDP
        bdp = max_throughput * 100 * 1e-6
        marking_threshold = bdp * 0.17
        # if the marking_threshold is smaller than the packet size set the
        # threshold to around two packets
        if (marking_threshold < avg_pkt_size):
            marking_threshold = avg_pkt_size * 2
        # also limit the marking threshold to 50KB
        elif marking_threshold > 50e3:
            marking_threshold = 50e3
        return marking_threshold

    def _apply_qdisc(self, port):
        """ Here be dragons... """
        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "root handle 1: hfsc default 10"
        # log.info(tc_cmd + cmd)
        # start_process(tc_cmd + cmd)
        # tc_cmd = "tc class add dev %s " % (port)
        # cmd = "parent 1: classid 1:10 hfsc sc rate %dbit ul rate %dbit" % (
        #     self.max_bps, self.max_bps)
        # log.info(tc_cmd + cmd)
        # start_process(tc_cmd + cmd)

        limit = int(self.max_queue)
        avg_pkt_size = 1500  # MTU packet size

        tc_cmd = "tc qdisc add dev %s " % (port)
        cmd = "root handle 1: htb default 10 "
        # cmd = "root handle 1: estimator 250msec 1sec htb default 10 "
        cmd += " direct_qlen %d " % (limit / avg_pkt_size)
        log.debug(tc_cmd + cmd)
        start_process(tc_cmd + cmd)
        tc_cmd = "tc class add dev %s " % (port)
        cmd = "parent 1: classid 1:10 htb rate %dbit burst %d" % (
            self.max_bps, self.max_bps)
        log.debug(tc_cmd + cmd)
        start_process(tc_cmd + cmd)

        if self.conf["tcp_policy"] == "dctcp":
            marking_threshold = self._calc_ecn(
                self.max_bps, avg_pkt_size)
            # Apply aggressive RED to mark excess packets in the queue
            max_q = limit / 4
            min_q = int(marking_threshold)
            tc_cmd = "tc qdisc add dev %s " % (port)
            cmd = "parent 1:10 handle 20:1 red "
            cmd += "limit %d " % (limit)
            cmd += "bandwidth  %dbit " % self.max_bps
            cmd += "avpkt %d " % avg_pkt_size
            cmd += "min %d " % min_q
            cmd += "max %d " % max_q
            # # Ballpark burst hard limit...
            burst = (min_q + min_q + max_q) / (3 * avg_pkt_size)
            cmd += "burst %d " % burst
            cmd += "probability 0.1"
            cmd += " ecn "
            log.debug(tc_cmd + cmd)
            start_process(tc_cmd + cmd)
        else:
            tc_cmd = "tc qdisc add dev %s " % (port)
            cmd = "parent 1:10 handle 20:1 bfifo "
            cmd += " limit %d" % limit
            start_process(tc_cmd + cmd)

        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "root handle 1 netem limit %d rate 10mbit" % (
        #     limit / avg_pkt_size)
        # log.info(tc_cmd + cmd)
        # start_process(tc_cmd + cmd)

        # limit = int(self.conf.max_queue)
        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "parent 1:10 handle 20: codel "
        # cmd += " limit %d" % (limit)
        # start_process(tc_cmd + cmd)

        # limit = int(self.conf.max_queue)
        # max_q = self.conf.max_queue / 4
        # min_q = max_q / 3
        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "parent 1:10 handle 20:1 sfq limit %d" % (
        #     self.conf.max_queue)
        # if self.dctcp:
        #     start_process("sysctl -w net.ipv4.tcp_ecn=1")
        #     cmd += "ecn "
        #     # cmd += "redflowlimit "
        #     # cmd += "min %d " % (min_q)
        #     # cmd += "max %d " % (max_q)
        #     # cmd += "probability 1"
        # log.info(tc_cmd + cmd)
        # start_process(tc_cmd + cmd)

        # Apply tc choke to mark excess packets in the queue with ecn
        # limit = int(self.conf.max_queue)
        # max_q = self.conf.max_queue
        # min_q = 400
        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "parent 1:10 handle 10:1 choke limit %d " % limit
        # cmd += "bandwidth  %dbit " % self.max_bps
        # cmd += "min %d " % (min_q)
        # cmd += "max %d " % (max_q)
        # cmd += "probability 0.001"
        # # if self.dctcp:
        # cmd += " ecn "
        # log.info(tc_cmd + cmd)
        # start_process(tc_cmd + cmd)

        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "parent 1:10 handle 30:1 fq_codel limit %d " % (
        #     self.conf.max_queue)
        # if ("dctcp" in self.conf) and self.conf["dctcp"]:
        #     start_process("sysctl -w net.ipv4.tcp_ecn=1")
        #     cmd += "ecn "
        # log.info(tc_cmd + cmd)
        # start_process(tc_cmd + cmd)

        start_process("ip link set %s txqueuelen %d" %
                      (port, limit / avg_pkt_size))
        start_process("ip link set %s mtu 1500" % port)

    def _config_links(self):
        for switch in self.net.switches:
            for port in switch.intfList():
                if port.name != "lo":
                    self._apply_qdisc(port)

    def _configure_hosts(self):
        for host in self.net.hosts:
            # Increase the maximum total buffer-space allocatable
            # This is measured in units of pages (4096 bytes)
            host.cmd("sysctl -w net.ipv4.tcp_window_scaling=1")
            host.cmd("sysctl -w net.ipv4.tcp_timestamps=1")
            host.cmd("sysctl -w net.ipv4.tcp_sack=1")
            host.cmd("sysctl -w net.ipv4.tcp_syn_retries=10")
            host.cmd("sysctl -w net.core.default_qdisc=pfifo_fast")
            # host.cmd("sysctl -w net.ipv4.tcp_recovery=0")
            if self.conf["tcp_policy"] == "dctcp":
                host.cmd("sysctl -w net.ipv4.tcp_congestion_control=dctcp")
                host.cmd("sysctl -w net.ipv4.tcp_ecn=1")
                host.cmd("sysctl -w net.ipv4.tcp_ecn_fallback=0")
            elif self.conf["tcp_policy"] == "tcp_nv":
                host.cmd("sysctl -w net.ipv4.tcp_congestion_control=nv")
            elif self.conf["tcp_policy"] == "pcc":
                host.cmd("sysctl -w net.ipv4.tcp_congestion_control=pcc")
        import time
        time.sleep(10)

    def _configure_network(self):
        c0 = RemoteController(self.switch_id + "c0")
        self.net.addController(c0)
        self._config_links()
        self._config_topo()
        self._configure_hosts()
        self._connect_controller(c0)
        log.info("Testing reachability after configuration...\n")
        # self.net.ping()
        # log.info("Testing bandwidth after configuration...\n")
        # self.net.iperf()

    def get_net(self):
        return self.net

    def get_topo(self):
        return self.topo

    def get_traffic_pattern(self, index):
        # start an all-to-all pattern if the list index is -1
        if index == -1:
            return "all"
        return self.conf["traffic_files"][index]

    def get_sw_ports(self):
        switches = self.net.switches
        sw_intfs = []
        for switch in switches:
            for intf in switch.intfNames():
                if intf is not 'lo':
                    sw_intfs.append(intf)
        return sw_intfs

    def get_num_sw_ports(self):
        sw_ports = 0
        for node, links in self.topo.ports.items():
            if self.topo.isSwitch(node):
                sw_ports += len(links)
        return sw_ports

    def get_host_ports(self):
        return self.host_ctrl_map.keys()

    def get_num_hosts(self):
        num_hosts = 0
        for node, links in self.topo.ports.items():
            if not self.topo.isSwitch(node):
                num_hosts += 1
        return num_hosts

    def _get_log_level(self, log_level):
        if 50:
            return "critical"
        if 40:
            return "error"
        if 30:
            return "warning"
        if 20:
            return "info"
        if 10:
            return "debug"
        if 0:
            return "output"

    def _create_network(self, cpu=-1):
        setLogLevel(self._get_log_level(log.level))
        self.topo.create_nodes()
        self.topo.create_links()

    def start_network(self):
        # Start Mininet
        host = custom(CPULimitedHost)
        self.net = Mininet(topo=self.topo,
                           controller=None, autoSetMacs=True)
        self.net.start()
        self._configure_network()
        self.started = True

    def stop_network(self):
        if self.started:
            log.info("Cleaning up topology and restoring all network variables.")
            if self.conf["tcp_policy"] == "dctcp":
                start_process("sysctl -w net.ipv4.tcp_ecn=0")
            # reset the active host congestion control to the previous value
            cmd = "sysctl -w net.ipv4.tcp_congestion_control=%s" % self.prev_cc
            start_process(cmd)
            # destroy the mininet
            self.net.stop()
            self.started = False
