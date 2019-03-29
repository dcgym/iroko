import os
from mininet.topo import Topo
from topos.topo_base import BaseTopo

DEFAULT_CONF = {
    "num_hosts": 16,            # number of hosts in the topology
    "traffic_files": ['stag_prob_0_2_3_data', 'stag_prob_1_2_3_data',
                      'stag_prob_2_2_3_data', 'stag_prob_0_5_3_data',
                      'stag_prob_1_5_3_data', 'stag_prob_2_5_3_data',
                      'stride1_data', 'stride2_data', 'stride4_data',
                      'stride8_data', 'random0_data', 'random1_data',
                      'random2_data', 'random0_bij_data', 'random1_bij_data',
                      'random2_bij_data', 'random_2_flows_data',
                      'random_3_flows_data', 'random_4_flows_data',
                      'hotspot_one_to_one_data'],
    "traffic_files": ['stride4_data'],
    "fanout": 4,
    "density": 2,
    "ecmp": True,
}


class Fattree(Topo):
    """ Class of Fattree Topology. """

    def __init__(self, fanout, density, switch_id):
        # Init Topo
        Topo.__init__(self)
        self.pod = fanout
        self.density = density
        self.core_switch_num = (fanout / 2)**2
        self.agg_switch_num = fanout * fanout / 2
        self.edge_switch_num = fanout * fanout / 2
        self.iHost = self.edge_switch_num * density
        self.switch_id = switch_id
        self.core_switches = []
        self.agg_switches = []
        self.edge_switches = []
        self.hostlist = []

    def create_nodes(self):
        self._add_switches(self.core_switch_num, 1, self.core_switches)
        self._add_switches(self.agg_switch_num, 2, self.agg_switches)
        self._add_switches(self.edge_switch_num, 3, self.edge_switches)
        self.create_hosts(self.iHost)

    def _add_switches(self, number, level, switch_list):
        """ Create switches. """
        for index in range(1, number + 1):
            sw_name = "%ss%d%d" % (self.switch_id, level, index)
            switch_list.append(self.addSwitch(sw_name))

    def create_hosts(self, num):
        """ Create hosts. """
        for i in range(1, num + 1):
            host_name = "h%d" % i
            self.hostlist.append(self.addHost(host_name, cpu=1.0 / num))

    def create_links(self):
        """ Add network links. """
        # Core to Agg
        end = self.pod / 2
        for switch in range(0, self.agg_switch_num, end):
            for i in range(0, end):
                for j in range(0, end):
                    self.addLink(
                        self.core_switches[i * end + j],
                        self.agg_switches[switch + i])
        # Agg to Edge
        for switch in range(0, self.agg_switch_num, end):
            for i in range(0, end):
                for j in range(0, end):
                    self.addLink(
                        self.agg_switches[switch +
                                          i], self.edge_switches[switch + j])
        # Edge to Host
        for switch in range(0, self.edge_switch_num):
            for i in range(0, self.density):
                self.addLink(
                    self.edge_switches[switch],
                    self.hostlist[self.density * switch + i])


class TopoConfig(BaseTopo):

    def __init__(self, conf={}):
        self.conf = DEFAULT_CONF
        self.conf.update(conf)
        BaseTopo.__init__(self, self.conf)
        self.name = "fattree"
        self.topo = Fattree(
            fanout=self.conf["fanout"], density=self.conf["density"],
            switch_id=self.switch_id)
        self._create_network()

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
            if j == topo.density + 1:
                j = 1
                i += 1

    def create_subnet_list(self, topo, num):
        """
            Create the subnet list of the certain Pod.
        """
        subnetlist = []
        remainder = num % (topo.pod / 2)
        if topo.pod == 4:
            if remainder == 0:
                subnetlist = [num - 1, num]
            elif remainder == 1:
                subnetlist = [num, num + 1]
            else:
                pass
        elif topo.pod == 8:
            if remainder == 0:
                subnetlist = [num - 3, num - 2, num - 1, num]
            elif remainder == 1:
                subnetlist = [num, num + 1, num + 2, num + 3]
            elif remainder == 2:
                subnetlist = [num - 1, num, num + 1, num + 2]
            elif remainder == 3:
                subnetlist = [num - 2, num - 1, num, num + 1]
            else:
                pass
        else:
            pass
        return subnetlist

    def _install_proactive(self, net, topo):
        """
            Install proactive flow entries for switches.
        """
        # Edge Switch
        for sw in topo.edge_switches:
            num = int(sw[-1:])

            # Downstream.
            for i in range(1, topo.density + 1):
                cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
                    'table=0,idle_timeout=0,hard_timeout=0,priority=40,arp, \
                    nw_dst=10.%d.0.%d,actions=output:%d'" % (sw, num, i,
                                                             topo.pod / 2 + i)
                os.system(cmd)
                cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
                    'table=0,idle_timeout=0,hard_timeout=0,priority=40,ip, \
                    nw_dst=10.%d.0.%d,actions=output:%d'" % (sw, num, i,
                                                             topo.pod / 2 + i)
                os.system(cmd)

            # Upstream.
            if topo.pod == 4:
                cmd = "ovs-ofctl add-group %s -O OpenFlow13 \
                'group_id=1,type=select,bucket=output:1,bucket=output:2'" % sw
            elif topo.pod == 8:
                cmd = "ovs-ofctl add-group %s -O OpenFlow13 \
                'group_id=1,type=select,bucket=output:1,bucket=output:2,\
                bucket=output:3,bucket=output:4'" % sw
            else:
                pass
            os.system(cmd)
            cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
            'table=0,priority=10,arp,actions=group:1'" % sw
            os.system(cmd)
            cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
            'table=0,priority=10,ip,actions=group:1'" % sw
            os.system(cmd)

        # Aggregate Switch
        for sw in topo.agg_switches:
            num = int(sw[-1:])
            subnetList = self.create_subnet_list(topo, num)

            # Downstream.
            k = 1
            for i in subnetList:
                cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
                    'table=0,idle_timeout=0,hard_timeout=0,priority=40,arp, \
                    nw_dst=10.%d.0.0/16, actions=output:%d'" % (sw, i,
                                                                topo.pod / 2 + k)
                os.system(cmd)
                cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
                    'table=0,idle_timeout=0,hard_timeout=0,priority=40,ip, \
                    nw_dst=10.%d.0.0/16, actions=output:%d'" % (sw, i,
                                                                topo.pod / 2 + k)
                os.system(cmd)
                k += 1

            # Upstream.
            if topo.pod == 4:
                cmd = "ovs-ofctl add-group %s -O OpenFlow13 \
                'group_id=1,type=select,bucket=output:1,bucket=output:2'" % sw
            elif topo.pod == 8:
                cmd = "ovs-ofctl add-group %s -O OpenFlow13 \
                'group_id=1,type=select,bucket=output:1,bucket=output:2,\
                bucket=output:3,bucket=output:4'" % sw
            else:
                pass
            os.system(cmd)
            cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
            'table=0,priority=10,arp,actions=group:1'" % sw
            os.system(cmd)
            cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
            'table=0,priority=10,ip,actions=group:1'" % sw
            os.system(cmd)

        # Core Switch
        for sw in topo.core_switches:
            j = 1
            k = 1
            for i in range(1, len(topo.edge_switches) + 1):
                cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
                    'table=0,idle_timeout=0,hard_timeout=0,priority=10,arp, \
                    nw_dst=10.%d.0.0/16, actions=output:%d'" % (sw, i, j)
                os.system(cmd)
                cmd = "ovs-ofctl add-flow %s -O OpenFlow13 \
                    'table=0,idle_timeout=0,hard_timeout=0,priority=10,ip, \
                    nw_dst=10.%d.0.0/16, actions=output:%d'" % (sw, i, j)
                os.system(cmd)
                k += 1
                if k == topo.pod / 2 + 1:
                    j += 1
                    k = 1

    def _config_topo(self):
        # Set hosts IP addresses.
        self._set_host_ip(self.net, self.topo)
        # Install proactive flow entries
        if self.conf["ecmp"]:
            self._install_proactive(self.net, self.topo)
