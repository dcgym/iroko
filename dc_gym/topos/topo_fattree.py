from topos.topo_base import BaseTopo
import dc_gym.utils as dc_utils
import logging
log = logging.getLogger(__name__)

DEFAULT_CONF = {
    # number of hosts in the topology
    "num_hosts": 16,
    "traffic_files": ["stag_prob_0_2_3_data", "stag_prob_1_2_3_data",
                      "stag_prob_2_2_3_data", "stag_prob_0_5_3_data",
                      "stag_prob_1_5_3_data", "stag_prob_2_5_3_data",
                      "stride1_data", "stride2_data", "stride4_data",
                      "stride8_data", "random0_data", "random1_data",
                      "random2_data", "random0_bij_data", "random1_bij_data",
                      "random2_bij_data", "random_2_flows_data",
                      "random_3_flows_data", "random_4_flows_data",
                      "hotspot_one_to_one_data"],
    "fanout": 4,
    "ecmp": True,
}


class IrokoTopo(BaseTopo):
    """ Class of Fattree Topology. """

    def __init__(self, conf={}):
        self.conf = DEFAULT_CONF
        self.conf.update(conf)
        BaseTopo.__init__(self, self.conf)
        self.name = "fattree"

        # Init Topo
        self.fanout = self.conf["fanout"]
        # check if fanout is valid
        if self.fanout not in [4, 8]:
            log.error("Invalid fanout!")
            return -1
        self.density = int(self.conf["num_hosts"] / (self.fanout**2 / 2))
        self.core_switch_num = int((self.fanout / 2)**2)
        self.agg_switch_num = int(self.fanout**2 / 2)
        self.edge_switch_num = int(self.fanout**2 / 2)
        self.core_switches = []
        self.agg_switches = []
        self.edge_switches = []

    def create_nodes(self):
        self._add_switches(self.core_switch_num, 1, self.core_switches)
        self._add_switches(self.agg_switch_num, 2, self.agg_switches)
        self._add_switches(self.edge_switch_num, 3, self.edge_switches)
        self.create_hosts(self.conf["num_hosts"])

    def _add_switches(self, number, level, switch_list):
        """ Create switches. """
        for index in range(1, number + 1):
            sw_name = "%ss%d%d" % (self.switch_id, level, index)
            switch_list.append(self.addSwitch(sw_name))

    def create_hosts(self, num):
        i = 1
        j = 1
        """ Create hosts. """
        for host_num in range(1, num + 1):
            host_name = "h%d" % host_num
            ip = "10.%d.0.%d" % (i, j)
            host = self.addHost(host_name, cpu=1.0 / num, ip=ip)
            self.host_ips[host] = ip
            self.host_list.append(host)
            j += 1
            if j == self.density + 1:
                j = 1
                i += 1

    def create_links(self):
        """ Add network links. """
        # Core to Agg
        end = int(self.fanout / 2)
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
                    self.host_list[self.density * switch + i])

    def create_subnet_list(self, num):
        """
            Create the subnet list of the certain Pod.
        """
        subnetlist = []
        remainder = num % (self.fanout / 2)
        if self.fanout == 4:
            if remainder == 0:
                subnetlist = [num - 1, num]
            elif remainder == 1:
                subnetlist = [num, num + 1]
            else:
                pass
        elif self.fanout == 8:
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

    def _install_proactive(self):
        """
            Install proactive flow entries for switches.
        """
        protocols = ["ip", "arp"]
        switches = self.edge_switches + self.agg_switches + self.core_switches
        for sw in switches:
            num = int(sw[-1:])
            ovs_flow_cmd = "ovs-ofctl add-flow %s -O OpenFlow13 " % sw
            ovs_grp_cmd = "ovs-ofctl add-group %s -O OpenFlow13 " % sw

            # Set upstream links of lower level switches
            if sw in self.edge_switches or sw in self.agg_switches:

                cmd = ovs_grp_cmd
                cmd += "group_id=1,type=select,"
                cmd += "bucket=output:1,bucket=output:2"
                if self.fanout == 8:
                    cmd += ",bucket=output:3,bucket=output:4"
                dc_utils.exec_process(cmd)

                # Configure entries per protocol
                for prot in protocols:
                    cmd = ovs_flow_cmd
                    cmd += "table=0,priority=10,%s,actions=group:1" % prot
                    dc_utils.exec_process(cmd)

            # Configure entries per protocol
            for prot in protocols:
                # Edge Switches
                if sw in self.edge_switches:
                    # Set downstream links
                    for i in range(1, self.density + 1):
                        cmd = ovs_flow_cmd
                        cmd += "table=0,idle_timeout=0,"
                        cmd += "hard_timeout=0,priority=40,"
                        cmd += "%s," % prot
                        cmd += "nw_dst=10.%d.0.%d," % (num, i)
                        cmd += "actions=output:%d" % (self.fanout / 2 + i)
                        dc_utils.exec_process(cmd)

                # Aggregation Switches
                if sw in self.agg_switches:
                    # Set downstream links
                    subnetList = self.create_subnet_list(num)
                    k = 1
                    for i in subnetList:
                        cmd = ovs_flow_cmd
                        cmd += "table=0,idle_timeout=0,"
                        cmd += "hard_timeout=0,priority=40,"
                        cmd += "%s," % prot
                        cmd += "nw_dst=10.%d.0.0/16," % i
                        cmd += "actions=output:%d" % (self.fanout / 2 + k)
                        dc_utils.exec_process(cmd)
                        k += 1

                # Core Switches
                if sw in self.core_switches:
                    # Set downstream links
                    j = 1
                    k = 1
                    for i in range(1, len(self.edge_switches) + 1):
                        cmd = ovs_flow_cmd
                        cmd += "table=0,idle_timeout=0,"
                        cmd += "hard_timeout=0,priority=10,"
                        cmd += "%s," % prot
                        cmd += "nw_dst=10.%d.0.0/16," % i
                        cmd += "actions=output:%d" % j
                        dc_utils.exec_process(cmd)
                        k += 1
                        if k == self.fanout / 2 + 1:
                            j += 1
                            k = 1

    def _config_topo(self):
        # Install proactive flow entries
        if self.conf["ecmp"]:
            self._install_proactive()
