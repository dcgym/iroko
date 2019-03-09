import os
import sys
import random
import string

from mininet.log import info, output, warn, error, debug
from mininet.node import RemoteController
from mininet.net import Mininet
from mininet.log import setLogLevel
from mininet.node import CPULimitedHost
from mininet.util import custom

cwd = os.getcwd()
FILE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, FILE_DIR)

DEFAULT_CONF = {
    "max_queue": 0.5e6,         # max queue of switches in bytes
    "max_capacity": 10e6,       # max bw capacity of link in bytes
    "min_rate": 0.1e6,          # min possible bw of an interface in bytes
    "parallel_envs": False,     # enable ids to support multiple topologies
    "tcp_policy": "tcp"
}


def merge_dicts(x, y):
    """Given two dicts, merge them into a new dict as a shallow copy."""
    z = x.copy()
    z.update(y)
    return z


class BaseTopo:

    def __init__(self, conf={}):
        self.conf = merge_dicts(DEFAULT_CONF, conf)
        self.name = "base"
        self.topo = None
        self.host_ctrl_map = {}
        self.host_ips = []
        self.net = None
        self.switch_id = self._generate_switch_id(self.conf)
        self.prev_cc = self._get_active_congestion_control()
        self._set_congestion_control(self.conf)

    def _generate_switch_id(self, conf):
        ''' Mininet needs unique ids if we want to launch
         multiple topologies at once '''
        if not conf["parallel_envs"]:
            return ""
        # Best collision-free technique for the limited amount of characters
        sw_id = ''.join(random.choice(''.join([random.choice(
                string.ascii_letters + string.digits)
            for ch in range(5)])) for _ in range(5))
        return sw_id

    def _get_active_congestion_control(self):
        prev_cc = os.popen("sysctl -n net.ipv4.tcp_congestion_control").read()
        return prev_cc

    def _set_congestion_control(self, conf):
        if conf["tcp_policy"] == "dctcp":
            os.system("modprobe tcp_dctcp")
            os.system("sysctl -w net.ipv4.tcp_ecn=1")
        elif conf["tcp_policy"] == "tcp_nv":
            os.system("modprobe tcp_nv")
        elif conf["tcp_policy"] == "pcc":
            if (os.popen("lsmod | grep pcc").read() == ""):
                os.system("insmod %s/tcp_pcc.ko" % FILE_DIR)

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

    def _apply_qdisc(self, port):
        """ Here be dragons... """
        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "root handle 1: hfsc default 10"
        # print (tc_cmd + cmd)
        # os.system(tc_cmd + cmd)
        # tc_cmd = "tc class add dev %s " % (port)
        # cmd = "parent 1: classid 1:10 hfsc sc rate %dbit ul rate %dbit" % (
        #     self.conf["max_capacity"], self.conf["max_capacity"])
        # print (tc_cmd + cmd)
        # os.system(tc_cmd + cmd)

        tc_cmd = "tc qdisc add dev %s " % (port)
        cmd = "root handle 1: htb default 10 "
        # cmd = "root handle 1: estimator 250msec 1sec htb default 10 "
        cmd += " direct_qlen 0 "
        debug(tc_cmd + cmd)
        os.system(tc_cmd + cmd)
        tc_cmd = "tc class add dev %s " % (port)
        cmd = "parent 1: classid 1:10 htb rate %dbit burst %d" % (
            self.conf["max_capacity"], self.conf["max_capacity"])
        debug(tc_cmd + cmd)
        os.system(tc_cmd + cmd)

        if self.conf["tcp_policy"] == "dctcp":
            # Apply aggressive RED to mark excess packets in the queue
            limit = int(self.conf["max_queue"])
            max_q = limit / 3
            min_q = max_q / 3
            tc_cmd = "tc qdisc add dev %s " % (port)
            cmd = "parent 1:10 handle 20:1 red "
            cmd += "limit %d " % (limit)
            cmd += "bandwidth  %dbit " % self.conf["max_capacity"]
            cmd += "avpkt 1000 "
            cmd += "min %d " % (min_q)
            cmd += "max %d " % (max_q)
            cmd += "probability 0.001"
            cmd += " ecn "
            debug(tc_cmd + cmd)
            os.system(tc_cmd + cmd)
        else:
            limit = int(self.conf["max_queue"])
            tc_cmd = "tc qdisc add dev %s " % (port)
            cmd = "parent 1:10 handle 20:1 bfifo "
            cmd += " limit %d" % (limit)
            os.system(tc_cmd + cmd)

        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "parent 1:10 handle 20:1 netem limit %d rate 10mbit" % (
        #     self.conf["max_queue"])
        # print (tc_cmd + cmd)
        # os.system(tc_cmd + cmd)

        # limit = int(self.conf["max_queue"])
        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "parent 1:10 handle 20: codel "
        # cmd += " limit %d" % (limit)
        # os.system(tc_cmd + cmd)

        # limit = int(self.conf["max_queue"])
        # max_q = self.conf["max_queue"] / 4
        # min_q = max_q / 3
        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "parent 1:10 handle 20:1 sfq limit %d" % (
        #     self.conf["max_queue"])
        # if self.dctcp:
        #     os.system("sysctl -w net.ipv4.tcp_ecn=1")
        #     cmd += "ecn "
        #     # cmd += "redflowlimit "
        #     # cmd += "min %d " % (min_q)
        #     # cmd += "max %d " % (max_q)
        #     # cmd += "probability 1"
        # print (tc_cmd + cmd)
        # os.system(tc_cmd + cmd)

        # Apply tc choke to mark excess packets in the queue with ecn
        # limit = int(self.conf["max_queue"])
        # max_q = self.conf["max_queue"]
        # min_q = 400
        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "parent 1:10 handle 10:1 choke limit %d " % limit
        # cmd += "bandwidth  %dbit " % self.conf["max_capacity"]
        # cmd += "min %d " % (min_q)
        # cmd += "max %d " % (max_q)
        # cmd += "probability 0.001"
        # # if self.dctcp:
        # cmd += " ecn "
        # print (tc_cmd + cmd)
        # os.system(tc_cmd + cmd)

        # tc_cmd = "tc qdisc add dev %s " % (port)
        # cmd = "parent 1:10 handle 30:1 fq_codel limit %d " % (
        #     self.conf["max_queue"])
        # if ("dctcp" in self.conf) and self.conf["dctcp"]:
        #     os.system("sysctl -w net.ipv4.tcp_ecn=1")
        #     cmd += "ecn "
        # print (tc_cmd + cmd)
        # os.system(tc_cmd + cmd)

        # os.system("ip link set %s txqueuelen 1" % (port))

    def _config_links(self):
        for switch in self.net.switches:
            for port in switch.intfList():
                if port.name != "lo":
                    self._apply_qdisc(port)

    def _configure_hosts(self):
        for host in self.net.hosts:
            # host.cmd("sysctl -w net.core.wmem_max=12582912")
            # host.cmd("sysctl -w net.core.rmem_max=12582912")
            # Increase the maximum total buffer-space allocatable
            # This is measured in units of pages (4096 bytes)
            # host.cmd("sysctl -w net.ipv4.tcp_mem='786432 1048576 26777216'")
            # host.cmd("sysctl -w net.ipv4.udp_mem='65536 131072 262144'")
            # host.cmd("sysctl -w net.ipv4.tcp_rmem='10240 87380 12582912'")
            # host.cmd("sysctl -w net.ipv4.udp_rmem='10240 87380 12582912'")
            # host.cmd("sysctl -w net.ipv4.tcp_wmem='10240 87380 12582912'")
            # host.cmd("sysctl -w net.ipv4.udp_wmem='10240 87380 12582912'")
            # host.cmd("sysctl -w net.ipv4.tcp_window_scaling=1")
            # host.cmd("sysctl -w net.ipv4.tcp_timestamps=1")
            # host.cmd("sysctl -w net.ipv4.tcp_sack=1")
            # host.cmd("sysctl -w net.ipv4.tcp_syn_retries=10")
            # host.cmd("sysctl -w net.core.default_qdisc=pfifo_fast")
            if self.conf["tcp_policy"] == "dctcp":
                host.cmd("sysctl -w net.ipv4.tcp_congestion_control=dctcp")
                host.cmd("sysctl -w net.ipv4.tcp_ecn=1")
                host.cmd("sysctl -w net.ipv4.tcp_ecn_fallback=0")
            elif self.conf["tcp_policy"] == "tcp_nv":
                host.cmd("sysctl -w net.ipv4.tcp_congestion_control=nv")
            elif self.conf["tcp_policy"] == "pcc":
                host.cmd("sysctl -w net.ipv4.tcp_congestion_control=pcc")

    def _configure_network(self):
        c0 = RemoteController(self.switch_id + "c0")
        self.net.addController(c0)
        self._config_links()
        self._config_topo()
        self._connect_controller(c0)
        self._configure_hosts()
        output("Testing reachability after configuration...\n")
        self.net.ping()
        # output("Testing bandwidth after configuration...\n")
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

    def get_host_ports(self):
        return self.host_ctrl_map.keys()

    def delete_topo(self):
        output("Cleaning up topology and restoring all network variables.")
        if self.conf["tcp_policy"] == "dctcp":
            os.system("sysctl -w net.ipv4.tcp_ecn=0")
        # reset the active host congestion control to the previous value
        cmd = "sysctl -w net.ipv4.tcp_congestion_control=%s" % self.prev_cc
        os.system(cmd)
        # destroy the mininet
        self.net.stop()

    def _create_network(self, cpu=-1):
        setLogLevel('warning')
        self.topo.create_nodes()
        self.topo.create_links()

        # Start Mininet
        host = custom(CPULimitedHost)
        net = Mininet(topo=self.topo,
                      controller=None, autoSetMacs=True)

        net.start()
        return net
