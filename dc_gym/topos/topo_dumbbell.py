import os
from topos.topo_base import BaseTopo, merge_dicts
from mininet.topo import Topo
from mininet.log import info, output, warn, error, debug


DEFAULT_CONF = {
    "num_hosts": 4,             # number of hosts in the topology
    "traffic_files": ['incast_2', 'incast_4', 'incast_8'],
}


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
        self.hosts_w = []
        self.hosts_e = []
        self.switchlist = []
        self.host_ips = []
        self.switch_id = switch_id

    def create_nodes(self):
        self._create_switches()
        self._create_hosts(self.num_hosts)

    def _create_switches(self):
        sw_w_name = self.switch_id + "s1"
        sw_e_name = self.switch_id + "s2"
        self.switch_w = self.addSwitch(name=sw_w_name)
        self.switch_e = self.addSwitch(name=sw_e_name)
        self.switchlist.append(self.switch_w)
        self.switchlist.append(self.switch_e)

    def _create_hosts(self, num):
        """
            Create hosts.
        """
        for i in range(1, num + 1):
            name = "h" + str(i)
            if (i % 2) == 1:
                ip = "10.1.0.%d" % ((i + 1) / 2)
                host = self.addHost(name=name, cpu=1.0 / num, ip=ip)
                self.hosts_w.append(host)
            else:
                ip = "10.2.0.%d" % ((i + 1) / 2)
                host = self.addHost(name=name, cpu=1.0 / num, ip=ip)
                self.hosts_e.append(host)
            output("Host %s IP %s\n" % (host, ip))
            self.host_ips.append(ip)

        self.hostlist = self.hosts_w + self.hosts_e

    def create_links(self):
        """
                Add links between switch and hosts.
        """
        self.addLink(self.switch_w, self.switch_e)
        for host in self.hosts_w:
            self.addLink(self.switch_w, host)
        for host in self.hosts_e:
            self.addLink(self.switch_e, host)


class TopoConfig(BaseTopo):

    def __init__(self, conf={}):
        conf = merge_dicts(DEFAULT_CONF, conf)
        BaseTopo.__init__(self, conf)
        self.name = "dumbbell"
        self.topo = DumbbellTopo(conf["num_hosts"], self.switch_id)
        self.net = self._create_network()
        self._configure_network()

    def _set_host_ip(self, net, topo):
        self.host_ips = self.topo.host_ips

    def _install_proactive(self, topo):
        """
                Install proactive flow entries for the switch.
        """
        for index, host in enumerate(topo.hosts_w):
            sw = topo.switch_w
            j = index + 1
            port = index + 2
            cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
                'table=0,idle_timeout=0,hard_timeout=0,priority=10,arp, \
                nw_dst=10.1.0.%d,actions=output:%d'" % (sw, j, port)
            os.system(cmd)
            cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
                'table=0,idle_timeout=0,hard_timeout=0,priority=10,ip, \
                nw_dst=10.1.0.%d,actions=output:%d'" % (sw, j, port)
            os.system(cmd)
        for index, host in enumerate(topo.hosts_e):
            sw = topo.switch_e
            j = index + 1
            port = index + 2
            cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
                'table=0,idle_timeout=0,hard_timeout=0,priority=10,arp, \
                nw_dst=10.2.0.%d,actions=output:%d'" % (sw, j, port)
            os.system(cmd)
            cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
                'table=0,idle_timeout=0,hard_timeout=0,priority=10,ip, \
                nw_dst=10.2.0.%d,actions=output:%d'" % (sw, j, port)
            os.system(cmd)

        cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
            'table=0,idle_timeout=0,hard_timeout=0,priority=10,ip, \
            nw_dst=10.2.0.0/24,actions=output:1'" % (topo.switch_w)
        os.system(cmd)
        cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
            'table=0,idle_timeout=0,hard_timeout=0,priority=10,arp, \
            nw_dst=10.2.0.0/24,actions=output:1'" % (topo.switch_w)
        os.system(cmd)
        cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
            'table=0,idle_timeout=0,hard_timeout=0,priority=10,ip, \
            nw_dst=10.1.0.0/24,actions=output:1'" % (topo.switch_e)
        os.system(cmd)
        cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
            'table=0,idle_timeout=0,hard_timeout=0,priority=10,arp, \
            nw_dst=10.1.0.0/24,actions=output:1'" % (topo.switch_e)
        os.system(cmd)

    def _config_topo(self):
        # Set hosts IP addresses.
        self._set_host_ip(self.net, self.topo)
        self._install_proactive(self.topo)
