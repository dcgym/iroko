import os
import sys
from mininet.topo import Topo
from topo_base import BaseTopo
parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parentdir)


class NonBlocking(Topo):
    """
            Class of NonBlocking Topology.
    """
    switchlist = []
    hostlist = []

    def __init__(self, k, switch_id):
        # Topo initiation
        Topo.__init__(self)
        self.pod = k
        self.core_switch = 1
        self.iHost = k**3 / 4
        self.switch_id = switch_id

    def create_nodes(self):
        self.create_core_switch(self.core_switch)
        self.create_host(self.iHost)

    def _add_switch(self, number, level, switch_list):
        """
                Create switches.
        """
        for i in range(1, number + 1):
            sw_name = "%s-%d-%d" % (self.switch_id, level, i)
            switch_list.append(self.addSwitch(sw_name))

    def create_core_switch(self, NUMBER):
        self._add_switch(NUMBER, 1, self.switchlist)

    def create_host(self, NUMBER):
        """
                Create hosts.
        """
        for i in range(1, NUMBER + 1):
            if i >= 100:
                PREFIX = "h"
            elif i >= 10:
                PREFIX = "h0"
            else:
                PREFIX = "h00"
            self.hostlist.append(self.addHost(
                PREFIX + str(i), cpu=1.0 / float(NUMBER)))

    def create_links(self, link_args):
        """
                Add links between switch and hosts.
        """
        for sw in self.switchlist:
            for host in self.hostlist:
                # use_htb=False
                self.addLink(sw, host, **link_args)


class TopoConfig(BaseTopo):
    NAME = "nonblock"
    NUM_HOSTS = 16  # the basic amount of hosts in the network
    TRAFFIC_FILES = ['stag_prob_0_2_3_data', 'stag_prob_1_2_3_data',
                     'stag_prob_2_2_3_data', 'stag_prob_0_5_3_data',
                     'stag_prob_1_5_3_data', 'stag_prob_2_5_3_data',
                     'stride1_data', 'stride2_data', 'stride4_data',
                     'stride8_data', 'random0_data', 'random1_data',
                     'random2_data', 'random0_bij_data', 'random1_bij_data',
                     'random2_bij_data', 'random_2_flows_data',
                     'random_3_flows_data', 'random_4_flows_data',
                     'hotspot_one_to_one_data']

    def __init__(self, options):
        BaseTopo.__init__(self, options)
        self.topo = NonBlocking(k=4, switch_id=self.switch_id)
        self.net = self._create_network()
        self._configure_network()

    def _set_host_ip(self, net, topo):
        hostlist = []
        for k in range(len(topo.hostlist)):
            hostlist.append(net.get(topo.hostlist[k]))
        i = 1
        j = 1
        for host in hostlist:
            ip = "10.%d.0.%d" % (i, j)
            host.setIP(ip)
            self.host_ips.append(ip)
            j += 1
            if j == 3:
                j = 1
                i += 1

    def _install_proactive(self, topo):
        """
                Install proactive flow entries for the switch.
        """
        for sw in topo.switchlist:
            i = 1
            j = 1
            for k in range(1, topo.iHost + 1):
                cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
                    'table=0,idle_timeout=0,hard_timeout=0,priority=40,arp, \
                    nw_dst=10.%d.0.%d,actions=output:%d'" % (sw, i, j, k)
                os.system(cmd)
                cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
                    'table=0,idle_timeout=0,hard_timeout=0,priority=40,ip, \
                    nw_dst=10.%d.0.%d,actions=output:%d'" % (sw, i, j, k)
                os.system(cmd)
                j += 1
                if j == 3:
                    j = 1
                    i += 1

    def _config_topo(self):
        # Set hosts IP addresses.
        self._set_host_ip(self.net, self.topo)
        self._install_proactive(self.topo)
