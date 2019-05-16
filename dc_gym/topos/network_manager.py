import os
import sys
from mininet.node import RemoteController
from mininet.net import Mininet

import dc_gym.utils as dc_utils
log = dc_utils.IrokoLogger.__call__().get_logger()

cwd = os.getcwd()
FILE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, FILE_DIR)


def get_congestion_control():
    prev_cc = os.popen("sysctl -n net.ipv4.tcp_congestion_control").read()
    return prev_cc


def load_congestion_control(tcp_policy):
    if tcp_policy == "dctcp":
        dc_utils.start_process("modprobe tcp_dctcp")
        dc_utils.start_process("sysctl -w net.ipv4.tcp_ecn=1")
    elif tcp_policy == "tcp_nv":
        dc_utils.start_process("modprobe tcp_nv")
    elif tcp_policy == "pcc":
        if (os.popen("lsmod | grep pcc").read() == ""):
            dc_utils.start_process("insmod %s/tcp_pcc.ko" % FILE_DIR)


def calc_ecn(max_throughput, avg_pkt_size):
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


class NetworkManager():

    def __init__(self, topo, tcp_policy="tcp"):
        self.topo = topo
        self.net = None
        self.host_ctrl_map = {}
        self.tcp_policy = tcp_policy
        self.prev_cc = get_congestion_control()
        load_congestion_control(tcp_policy)
        self.start_network()

    def _apply_qdisc(self, port):
        """ Here be dragons... """
        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "root handle 1: hfsc default 10"
        # log.info(tc_cmd + cmd)
        # dc_utils.start_process(tc_cmd + cmd)
        # tc_cmd = "tc class add dev %s " % (port)
        # cmd = "parent 1: classid 1:10 hfsc sc rate %dbit ul rate %dbit" % (
        #     self.topo.max_bps, self.topo.max_bps)
        # log.info(tc_cmd + cmd)
        # dc_utils.start_process(tc_cmd + cmd)

        limit = int(self.topo.max_queue)
        avg_pkt_size = 1500  # MTU packet size

        tc_cmd = "tc qdisc add dev %s " % (port)
        cmd = "root handle 1: htb default 10 "
        # cmd = "root handle 1: estimator 250msec 1sec htb default 10 "
        cmd += " direct_qlen %d " % (limit / avg_pkt_size)
        log.debug(tc_cmd + cmd)
        dc_utils.start_process(tc_cmd + cmd)
        tc_cmd = "tc class add dev %s " % (port)
        cmd = "parent 1: classid 1:10 htb rate %dbit burst %d" % (
            self.topo.max_bps, self.topo.max_bps)
        log.debug(tc_cmd + cmd)
        dc_utils.start_process(tc_cmd + cmd)

        if self.tcp_policy == "dctcp":
            marking_threshold = calc_ecn(self.topo.max_bps, avg_pkt_size)
            # Apply aggressive RED to mark excess packets in the queue
            max_q = limit / 4
            min_q = int(marking_threshold)
            tc_cmd = "tc qdisc add dev %s " % (port)
            cmd = "parent 1:10 handle 20:1 red "
            cmd += "limit %d " % (limit)
            cmd += "bandwidth  %dbit " % self.topo.max_bps
            cmd += "avpkt %d " % avg_pkt_size
            cmd += "min %d " % min_q
            cmd += "max %d " % max_q
            # # Ballpark burst hard limit...
            burst = (min_q + min_q + max_q) / (3 * avg_pkt_size)
            cmd += "burst %d " % burst
            cmd += "probability 0.1"
            cmd += " ecn "
            log.debug(tc_cmd + cmd)
            dc_utils.start_process(tc_cmd + cmd)
        else:
            tc_cmd = "tc qdisc add dev %s " % (port)
            cmd = "parent 1:10 handle 20:1 bfifo "
            cmd += " limit %d" % limit
            dc_utils.start_process(tc_cmd + cmd)

        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "root handle 1 netem limit %d rate 10mbit" % (
        #     limit / avg_pkt_size)
        # log.info(tc_cmd + cmd)
        # dc_utils.start_process(tc_cmd + cmd)

        # limit = int(self.topo.max_queue)
        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "parent 1:10 handle 20: codel "
        # cmd += " limit %d" % (limit)
        # dc_utils.start_process(tc_cmd + cmd)

        # limit = int(self.topo.max_queue)
        # max_q = self.topo.max_queue / 4
        # min_q = max_q / 3
        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "parent 1:10 handle 20:1 sfq limit %d" % (
        #     self.topo.max_queue)
        # if self.dctcp:
        #     dc_utils.start_process("sysctl -w net.ipv4.tcp_ecn=1")
        #     cmd += "ecn "
        #     # cmd += "redflowlimit "
        #     # cmd += "min %d " % (min_q)
        #     # cmd += "max %d " % (max_q)
        #     # cmd += "probability 1"
        # log.info(tc_cmd + cmd)
        # dc_utils.start_process(tc_cmd + cmd)

        # Apply tc choke to mark excess packets in the queue with ecn
        # limit = int(self.topo.max_queue)
        # max_q = self.topo.max_queue
        # min_q = 400
        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "parent 1:10 handle 10:1 choke limit %d " % limit
        # cmd += "bandwidth  %dbit " % self.topo.max_bps
        # cmd += "min %d " % (min_q)
        # cmd += "max %d " % (max_q)
        # cmd += "probability 0.001"
        # # if self.dctcp:
        # cmd += " ecn "
        # log.info(tc_cmd + cmd)
        # dc_utils.start_process(tc_cmd + cmd)

        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "parent 1:10 handle 30:1 fq_codel limit %d " % (
        #     self.topo.max_queue)
        # if ("dctcp" in self.conf) and self.conf["dctcp"]:
        #     dc_utils.start_process("sysctl -w net.ipv4.tcp_ecn=1")
        #     cmd += "ecn "
        # log.info(tc_cmd + cmd)
        # dc_utils.start_process(tc_cmd + cmd)

        dc_utils.start_process("ip link set %s txqueuelen %d" %
                               (port, limit / avg_pkt_size))
        dc_utils.start_process("ip link set %s mtu 1500" % port)

    def _connect_controller(self, net):
        controller = RemoteController(self.topo.switch_id + "_c")
        net.addController(controller)
        for i, host in enumerate(self.topo.host_list):
            # Configure host
            net.addLink(controller, host)
            # Configure controller
            ctrl_iface = "%s_c-eth%d" % (self.topo.switch_id, i)

            for index, switch in self.topo.ports[host].items():
                switch_iface = switch[0] + "-eth" + str(switch[1])
                self.host_ctrl_map[switch_iface] = ctrl_iface

    def _config_links(self, net):
        for switch in net.switches:
            for port in switch.intfList():
                if port.name != "lo":
                    self._apply_qdisc(port)

    def _config_hosts(self, net):
        for host in net.hosts:
            # Increase the maximum total buffer-space allocatable
            # This is measured in units of pages (4096 bytes)
            dc_utils.start_mn_process(
                "sysctl -w net.ipv4.tcp_window_scaling=1", host)
            dc_utils.start_mn_process(
                "sysctl -w net.ipv4.tcp_timestamps=1", host)
            dc_utils.start_mn_process("sysctl -w net.ipv4.tcp_sack=1", host)
            dc_utils.start_mn_process(
                "sysctl -w net.ipv4.tcp_syn_retries=10", host)
            dc_utils.start_mn_process(
                "sysctl -w net.core.default_qdisc=pfifo_fast", host)
            # dc_utils.start_mn_process("sysctl -w net.ipv4.tcp_recovery=0")
            if self.tcp_policy == "dctcp":
                dc_utils.start_mn_process(
                    "sysctl -w net.ipv4.tcp_congestion_control=dctcp", host)
                dc_utils.start_mn_process("sysctl -w net.ipv4.tcp_ecn=1", host)
                dc_utils.start_mn_process(
                    "sysctl -w net.ipv4.tcp_ecn_fallback=0", host)
            elif self.tcp_policy == "tcp_nv":
                dc_utils.start_mn_process(
                    "sysctl -w net.ipv4.tcp_congestion_control=nv", host)
            elif self.tcp_policy == "pcc":
                dc_utils.start_mn_process(
                    "sysctl -w net.ipv4.tcp_congestion_control=pcc", host)

    def _config_network(self, net):
        self.topo._config_topo()
        self._config_links(net)
        self._config_hosts(net)
        self._connect_controller(net)
        # log.info("Testing reachability after configuration...\n")
        # net.ping()
        # log.info("Testing bandwidth after configuration...\n")
        # net.iperf()

    def get_net(self):
        return self.net

    def get_topo(self):
        return self.topo

    def get_sw_ports(self):
        switches = self.net.switches
        sw_intfs = []
        for switch in switches:
            for intf in switch.intfNames():
                if intf is not 'lo':
                    sw_intfs.append(intf)
        return sw_intfs

    def get_host_ports(self):
        return self.host_ctrl_map.keys()

    def start_network(self):
        # Start Mininet
        self.net = Mininet(topo=self.topo, controller=None, autoSetMacs=True)
        self.net.start()
        self._config_network(self.net)

    def stop_network(self):
        log.info("Removing interfaces and restoring all network state.")
        if self.tcp_policy == "dctcp":
            dc_utils.start_process("sysctl -w net.ipv4.tcp_ecn=0")
        # reset the active host congestion control to the previous value
        cmd = "sysctl -w net.ipv4.tcp_congestion_control=%s" % self.prev_cc
        dc_utils.start_process(cmd)
        # destroy all virtual interfaces and switches
        try:
            self.net.stop()
        except Exception as e:
            log.error('Failed to delete the virtual network:\n' + str(e))
