import os
import sys
from mininet.topo import Topo
from topo_base import BaseTopo

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parentdir)


class DumbbellTopo(Topo):
    """
            Class of Dumbbell Topology.
    """

    def __init__(self, hosts, switch_id):
        # Topo initiation
        Topo.__init__(self)
        self.num_hosts = hosts
        self.switch_w = None
        self.switch_e = None
        self.hostlist = []
        self.switchlist = []
        self.switch_id = switch_id

    def create_nodes(self):
        self._create_switches()
        self._create_hosts(self.num_hosts)

    def _create_switches(self):
        sw_w_name = self.switch_id + "sw1"
        sw_e_name = self.switch_id + "sw2"
        self.switch_w = self.addSwitch(name=sw_w_name, failMode='standalone')
        self.switch_e = self.addSwitch(name=sw_e_name, failMode='standalone')
        self.switchlist.append(self.switch_w)
        self.switchlist.append(self.switch_e)

    def _create_hosts(self, num):
        """
            Create hosts.
        """
        for i in range(1, num + 1):
            self.hostlist.append(self.addHost("h" + str(i), cpu=1.0 / num))

    def create_links(self, link_args):
        """
                Add links between switch and hosts.
        """
        for i, host in enumerate(self.hostlist):
            if i < len(self.hostlist) / 2:
                self.addLink(self.switch_w, host, **link_args)
            else:
                self.addLink(self.switch_e, host, **link_args)
        self.addLink(self.switch_w, self.switch_e, **link_args)


class TopoConfig(BaseTopo):
    NAME = "dumbbell"
    NUM_HOSTS = 4   # the basic amount of hosts in the network
    TRAFFIC_FILES = ['incast_2']
    LABELS = ['incast']

    def __init__(self, options):
        BaseTopo.__init__(self, options)
        self.topo = DumbbellTopo(self.NUM_HOSTS, self.switch_id)
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

    def _config_topo(self):
        # Set hosts IP addresses.
        self._set_host_ip(self.net, self.topo)
