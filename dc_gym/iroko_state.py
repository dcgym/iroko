from multiprocessing import RawArray
from ctypes import c_ulong, c_ubyte
import numpy as np

from dc_gym.monitor.iroko_monitor import BandwidthCollector
from dc_gym.monitor.iroko_monitor import QueueCollector
from dc_gym.monitor.iroko_monitor import FlowCollector
from dc_gym.iroko_reward import RewardFunction
import dc_gym.utils as dc_utils
import logging
log = logging.getLogger(__name__)


class StateManager:
    __slots__ = ["num_ports", "deltas", "prev_stats", "stats_keys",
                 "stats_dict", "dopamin", "stats", "flow_stats", "procs",
                 "collect_flows", "reward_model"]

    def __init__(self, conf, net_man, stats_dict):
        self.stats = None
        self.prev_stats = None
        self.flow_stats = None
        self.deltas = None
        self.procs = []
        self.stats_dict = stats_dict

        self.stats_keys = conf["state_model"]
        self.collect_flows = conf["collect_flows"]
        self.reward_model = conf["reward_model"]

        self.num_ports = net_man.get_num_sw_ports()
        num_hosts = net_man.get_num_hosts()
        self.dopamin = RewardFunction(self.reward_model, self.stats_dict)
        self._init_stats_matrices(self.num_ports, num_hosts)
        self._spawn_collectors(net_man)

    def stop(self):
        self.stats.fill(0)
        self.prev_stats.fill(0)

    def close(self):
        self.stop()
        self._terminate_collectors()

    def _init_stats_matrices(self, num_ports, num_hosts):
        # Set up the shared stats matrix
        stats_arr_len = num_ports * len(self.stats_dict)
        mp_stats = RawArray(c_ulong, stats_arr_len)
        np_stats = dc_utils.shmem_to_nparray(mp_stats, np.float64)
        self.stats = np_stats.reshape((len(self.stats_dict), num_ports))
        # Set up the shared flow matrix
        if (self.collect_flows):
            flow_arr_len = num_ports * num_hosts * 2
            mp_flows = RawArray(c_ubyte, flow_arr_len)
            np_flows = dc_utils.shmem_to_nparray(mp_flows, np.uint8)
            self.flow_stats = np_flows.reshape((num_ports, 2, num_hosts))
        # Save the initialized stats matrix to compute deltas
        self.prev_stats = self.stats.copy()
        self.deltas = np.zeros(shape=(len(self.stats_dict), num_ports))

    def _spawn_collectors(self, net_man):
        sw_ports = net_man.get_sw_ports()
        host_ports = net_man.get_host_ports()
        # Launch an asynchronous queue collector
        proc = QueueCollector(
            sw_ports, self.stats, self.stats_dict, net_man.topo.max_queue)
        proc.start()
        self.procs.append(proc)
        # Launch an asynchronous bandwidth collector
        proc = BandwidthCollector(
            host_ports, self.stats, self.stats_dict, net_man.topo.max_bps)
        proc.start()
        self.procs.append(proc)
        # Launch an asynchronous flow collector
        if (self.collect_flows):
            host_ips = net_man.topo.host_ips.values()
            proc = FlowCollector(sw_ports, host_ips, self.flow_stats)
            proc.start()
            self.procs.append(proc)

    def _terminate_collectors(self):
        for proc in self.procs:
            if proc is not None:
                proc.terminate()

    def _compute_deltas(self, stats_prev, stats_now):
        self.deltas = stats_now - stats_prev
        self.deltas[self.deltas < 0] = -1
        self.deltas[self.deltas > 0] = 1

    def get_stats(self):
        return self.stats

    def observe(self):
        obs = []
        # retrieve the current deltas before updating total values
        self._compute_deltas(self.prev_stats, self.stats)
        self.prev_stats = self.stats.copy()
        # Create the data matrix for the agent based on the collected stats
        for index in range(self.num_ports):
            for key in self.stats_keys:
                if (key.startswith("d_")):
                    # remove the first two chars and get the actual key
                    obs.append(self.deltas[self.stats_dict[key[2:]]][index])
                else:
                    obs.append(self.stats[self.stats_dict[key]][index])
            if self.collect_flows:
                obs.extend(self.flow_stats[index])
        return obs

    def get_reward(self, curr_action):
        # Compute the reward
        return self.dopamin.get_reward(self.stats, curr_action)
