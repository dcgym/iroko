import os
import random
import string

from mininet.log import info, output, warn, error, debug
from mininet.node import RemoteController
from mininet.net import Mininet
from mininet.log import setLogLevel
from mininet.node import CPULimitedHost
from mininet.util import custom


class BaseTopo():
    NAME = "base"
    MAX_QUEUE = 500         # max queue of all switches
    MAX_CAPACITY = 10e6     # Max bw capacity of link in bytes
    MIN_RATE = 6.25e5       # minimal possible bw of an interface in bytes

    def __init__(self, options):
        self.options = options
        self.num_hosts = self.NUM_HOSTS
        self.topo = None
        self.host_ctrl_map = {}
        self.host_ips = []
        self.switch_id = self.generate_switch_id()

    def generate_switch_id(self):

        # Best collision-free technique for the limited amount of characters
        sw_id = ''.join(random.choice(''.join([random.choice(
            string.ascii_letters + string.digits)
            for ch in range(5)])) for _ in range(5))
        return sw_id

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

        # Set the max queue and bandwidth of the network
        tc_cmd = "tc qdisc add dev %s " % (port)
        cmd = "root handle 1: netem limit %d rate %dbit" % (
            self.MAX_QUEUE, self.MAX_CAPACITY)
        os.system(tc_cmd + cmd)

        # Apply tc choke to mark excess packets in the queue with ecn
        limit = int(self.MAX_QUEUE)
        # max_q = self.MAX_QUEUE /4
        # min_q = max_q /3
        tc_cmd = "tc qdisc add dev %s " % (port)
        cmd = "parent 1:1 handle 2: choke limit %d " % limit
        cmd += "bandwidth  %dbit " % self.MAX_CAPACITY
        if ("is_dctcp" in self.options) and self.options["is_dctcp"]:
            cmd += "ecn "
        # cmd += "min %d " % (min_q)
        # cmd += "max %d " % (max_q)
        # cmd += "probability 1"
        os.system(tc_cmd + cmd)

    def _config_links(self):
        for switch in self.net.switches:
            for port in switch.intfList():
                if port.name != "lo":
                    self._apply_qdisc(port)

    def _configure_hosts(self):
        if ("is_nv" in self.options):
            os.system("modprobe tcp_nv")
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
            if ("is_dctcp" in self.options and self.options["is_dctcp"]):
                os.system("modprobe tcp_dctcp")
                host.cmd("sysctl -w net.ipv4.tcp_congestion_control=dctcp")
                host.cmd("sysctl -w net.ipv4.tcp_ecn=1")
                host.cmd("sysctl -w net.ipv4.tcp_ecn_fallback=0")
            if ("is_nv" in self.options and self.options["is_nv"]):
                host.cmd("sysctl -w net.ipv4.tcp_congestion_control=nv")

    def _configure_network(self):
        c0 = RemoteController(self.switch_id + "c0")
        self.net.addController(c0)
        # quick and dirty queue fix
        for switch in self.net.switches:
            for iface in switch.intfList():
                os.system("ip link set %s txqueuelen %d" %
                          (iface, self.MAX_QUEUE))
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

    def get_sw_ports(self):
        switches = self.net.switches
        sw_intfs = []
        for switch in switches:
            for intf in switch.intfNames():
                if intf is not 'lo':
                    sw_intfs.append(intf)
        return sw_intfs

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
