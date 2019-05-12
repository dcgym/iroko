from topos.topo_base import BaseTopo
from dc_gym.utils import *
log = IrokoLogger("iroko")

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
}


class IrokoTopo(BaseTopo):

    def __init__(self, conf={}):
        self.conf = DEFAULT_CONF
        self.conf.update(conf)
        BaseTopo.__init__(self, self.conf)
        self.name = "dumbbell"
        self.core_switch = None

    def create_nodes(self):
        self.create_core_switch()
        self.create_hosts(self.conf["num_hosts"])

    def create_core_switch(self):
        sw_name = "%ss1" % self.switch_id
        self.core_switch = self.addSwitch(sw_name)

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
            if j == 3:
                j = 1
                i += 1

    def create_links(self):
        """
                Add links between switch and hosts.
        """
        for host in self.host_list:
            self.addLink(self.core_switch, host)

    def _install_proactive(self):
        """
                Install proactive flow entries for the switch.
        """
        protocols = ["ip", "arp"]
        # West Switch
        ovs_flow_cmd = "ovs-ofctl add-flow %s " % self.core_switch
        ovs_flow_cmd += "-O OpenFlow13 "
        for prot in protocols:
            i = 1
            j = 1
            for k in range(1, self.conf["num_hosts"] + 1):
                cmd = ovs_flow_cmd
                cmd += "table=0,idle_timeout=0,"
                cmd += "hard_timeout=0,priority=10,"
                cmd += "nw_dst=10.%d.0.%d," % (i, j)
                cmd += "%s," % prot
                cmd += "actions=output:%d" % k
                start_process(cmd)
                j += 1
                if j == 3:
                    j = 1
                    i += 1

    def _config_topo(self):
        # Set hosts IP addresses.
        self._install_proactive()
