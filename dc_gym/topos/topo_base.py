import os
import sys
from mininet.log import setLogLevel
from mininet.topo import Topo

from dc_gym.utils import *

log = IrokoLogger("iroko")

cwd = os.getcwd()
FILE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, FILE_DIR)

DEFAULT_CONF = {
    "max_capacity": 10e6,       # max bw capacity of link in bytes
    "min_capacity": 0.1e6,      # min possible bw of an interface in bytes
    "num_hosts": "0",           # the initial number of hosts is zero
    "id": ""                    # ids support multiple topologies
}


def calculate_max_queue(max_bps):
    queue = 4e6
    if max_bps < 1e9:
        queue = 4e6 / (1e9 / max_bps)
        # keep a sensible minimum size
        if queue < 4e5:
            queue = 4e5
    return queue


def get_log_level(log_level):
    if log_level == 50:
        return "critical"
    elif log_level == 40:
        return "error"
    elif log_level == 30:
        return "warning"
    elif log_level == 20:
        return "info"
    elif log_level == 10:
        return "debug"
    else:
        return "output"


class BaseTopo(Topo):

    def __init__(self, conf={}):
        Topo.__init__(self)
        self.conf = DEFAULT_CONF
        self.conf.update(conf)
        self.name = "base"
        self.host_list = []
        self.host_ips = {}
        self.max_bps = self.conf["max_capacity"]
        self.switch_id = self.conf["id"]
        self.max_queue = calculate_max_queue(self.max_bps)
        setLogLevel(get_log_level(log.level))

    def _config_topo(self, ovs_v, is_ecmp):
        raise NotImplementedError("Method _config_topo not implemented!")

    def get_traffic_pattern(self, index):
        # start an all-to-all pattern if the list index is -1
        if index == -1:
            return "all"
        return self.conf["traffic_files"][index]

    def create_topo(self):
        self.create_nodes()
        self.create_links()

    def get_num_sw_ports(self):
        sw_ports = 0
        for node, links in self.ports.items():
            if self.isSwitch(node):
                sw_ports += len(links)
        return sw_ports

    def get_num_hosts(self):
        return self.conf["num_hosts"]
