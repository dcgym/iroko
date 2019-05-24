from multiprocessing import Array
from ctypes import c_ulong, c_ubyte
import numpy as np
from klepto.archives import hdfdir_archive

from dc_gym.monitor.iroko_monitor import BandwidthCollector
from dc_gym.monitor.iroko_monitor import QueueCollector
from dc_gym.monitor.iroko_monitor import FlowCollector
from dc_gym.iroko_reward import RewardFunction
import dc_gym.utils as dc_utils
import logging
log = logging.getLogger(__name__)


class StateManager:
    __slots__ = ["num_ports", "deltas", "prev_stats", "stats_file",
                 "stats_keys", "stats_dict", "stats_samples", "dopamin",
                 "stats", "flow_stats", "procs", "collect_flows",
                 "reward_model"]

    def __init__(self, conf, topo, stats_dict):
        self.stats = None
        self.prev_stats = None
        self.flow_stats = None
        self.deltas = None
        self.stats_samples = None
        self.procs = []
        self.stats_dict = stats_dict

        self.stats_file = "%s/statistics" % conf["output_dir"]
        self.stats_keys = conf["state_model"]
        self.collect_flows = conf["collect_flows"]
        self.reward_model = conf["reward_model"]

        self.num_ports = topo.get_num_sw_ports()
        self._init_stats_matrices(self.num_ports, topo.get_num_hosts())

    def start(self, net_man):
        self._set_data_checkpoints()
        self._spawn_collectors(net_man)
        self.dopamin = RewardFunction(self.reward_model, self.stats_dict)

    def stop(self):
        self._terminate_collectors()

        log.info("Writing collected data to disk")
        try:
            self._flush()
        except Exception as e:
            log.error("Error flushing file %s" % self.stats_file, e)
        if self.stats_samples:
            self.stats_samples = None
        self.stats.fill(0)
        self.prev_stats.fill(0)

    def close(self):
        self.stop()

    def _init_stats_matrices(self, num_ports, num_hosts):
        # Set up the shared stats matrix
        stats_arr_len = num_ports * len(self.stats_dict)
        mp_stats = Array(c_ulong, stats_arr_len)
        np_stats = dc_utils.shmem_to_nparray(mp_stats, np.float64)
        self.stats = np_stats.reshape((len(self.stats_dict), num_ports))
        # Set up the shared flow matrix
        if (self.collect_flows):
            flow_arr_len = num_ports * num_hosts * 2
            mp_flows = Array(c_ubyte, flow_arr_len)
            np_flows = dc_utils.shmem_to_nparray(mp_flows, np.uint8)
            self.flow_stats = np_flows.reshape((num_ports, 2, num_hosts))
        # Save the initialized stats matrix to compute deltas
        self.prev_stats = self.stats.copy()
        self.deltas = np.zeros(shape=(len(self.stats_dict), num_ports))

    def _spawn_collectors(self, net_man):
        sw_ports = net_man.get_sw_ports()
        host_ports = net_man.get_host_ports()
        host_ips = net_man.topo.host_ips.values()
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
            proc = FlowCollector(sw_ports, host_ips, self.flow_stats)
            proc.start()
            self.procs.append(proc)

    def _set_data_checkpoints(self):
        # define file name
        self.stats_samples = hdfdir_archive(self.stats_file, {}, cached=True)
        self.stats_samples["reward"] = []
        self.stats_samples["actions"] = []
        self.stats_samples["stats"] = []

    def _terminate_collectors(self):
        for proc in self.procs:
            if proc is not None:
                proc.terminate()

    def _compute_deltas(self, num_ports, stats_prev, stats_now):
        self.deltas = stats_now - stats_prev
        self.deltas[self.deltas < 0] = -1
        self.deltas[self.deltas > 0] = 1

    def observe(self, curr_action, do_sample):
        obs = []
        # retrieve the current deltas before updating total values
        self._compute_deltas(self.num_ports, self.prev_stats, self.stats)
        self.prev_stats = self.stats.copy()
        # Create the data matrix for the agent based on the collected stats
        for index in range(self.num_ports):
            state = []
            for key in self.stats_keys:
                if (key.startswith("d_")):
                    state.append(self.deltas[self.stats_dict[key[2:]]][index])
                else:
                    state.append(self.stats[self.stats_dict[key]][index])
            if self.collect_flows:
                state.extend(self.flow_stats[index])
            obs.append(np.array(state))
        # Compute the reward
        reward = self.dopamin.get_reward(self.stats, curr_action)

        if (do_sample):
            # Save collected data
            self.stats_samples["stats"].append(self.stats.copy())
            self.stats_samples["reward"].append(reward)
            self.stats_samples["actions"].append(curr_action.copy())
        return np.array(obs), reward

    def _flush(self):
        if self.stats_samples:
            log.info("Saving statistics...")
            self.stats_samples.sync()
            self.stats_samples.dump()
            # np.save(self.stats_file, self.stats_samples)
            log.info("Done saving statistics...")
