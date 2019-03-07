from filelock import FileLock
from multiprocessing import Array
from ctypes import c_ulong, c_ubyte
import numpy as np

from dc_gym.monitor.iroko_monitor import BandwidthCollector
from dc_gym.monitor.iroko_monitor import QueueCollector
from dc_gym.monitor.iroko_monitor import FlowCollector
from iroko_reward import RewardFunction


def shmem_to_nparray(shmem_array, dtype):
    return np.frombuffer(shmem_array.get_obj(), dtype=dtype)


class StateManager:
    STATS_DICT = {"backlog": 0, "olimit": 1,
                  "drops": 2, "bw_rx": 3, "bw_tx": 4}
    REWARD_MODEL = ["backlog", "action"]
    STATS_KEYS = ["backlog"]
    DELTA_KEYS = []
    COLLECT_FLOWS = False
    __slots__ = ["num_features", "num_ports", "deltas", "prev_stats",
                 "stats_file", "data", "dopamin", "stats", "flow_stats",
                 "procs"]

    def __init__(self, topo_conf, config):
        sw_ports = topo_conf.get_sw_ports()
        self.num_ports = len(sw_ports)
        self.deltas = None
        self.prev_stats = None
        self._set_feature_length(len(topo_conf.host_ips))
        self._init_stats_matrices(self.num_ports, len(topo_conf.host_ips))
        self._spawn_collectors(sw_ports, topo_conf.host_ips)
        self.dopamin = RewardFunction(topo_conf.host_ctrl_map,
                                      sw_ports, self.REWARD_MODEL,
                                      topo_conf.MAX_QUEUE,
                                      topo_conf.MAX_CAPACITY, self.STATS_DICT)
        self._set_data_checkpoints(config)

    def flush_and_close(self):
        print("Writing collected data to disk")
        with FileLock(self.stats_file.name + ".lock"):
            try:
                self.flush()
            except Exception as e:
                print("Error flushing file %s" % self.stats_file.name, e)
        self.stats_file.close()

    def terminate(self):
        self._terminate_collectors()

    def reset(self):
        pass        # self.flush()

    def _set_feature_length(self, num_hosts):
        self.num_features = len(self.STATS_KEYS)
        self.num_features += len(self.DELTA_KEYS)
        if self.COLLECT_FLOWS:
            # There are two directions for flows, src and destination
            self.num_features += num_hosts * 2

    def get_feature_length(self):
        return self.num_features

    def _init_stats_matrices(self, num_ports, num_hosts):
        self.stats = None
        self.flow_stats = None
        self.procs = []
        # Set up the shared stats matrix
        stats_arr_len = num_ports * len(self.STATS_DICT)
        mp_stats = Array(c_ulong, stats_arr_len)
        np_stats = shmem_to_nparray(mp_stats, np.int64)
        self.stats = np_stats.reshape((len(self.STATS_DICT), num_ports))
        # Set up the shared flow matrix
        flow_arr_len = num_ports * num_hosts * 2
        mp_flows = Array(c_ubyte, flow_arr_len)
        np_flows = shmem_to_nparray(mp_flows, np.uint8)
        self.flow_stats = np_flows.reshape((num_ports, 2, num_hosts))
        # Save the initialized stats matrix to compute deltas
        self.prev_stats = self.stats.copy()
        self.deltas = np.zeros(shape=(len(self.STATS_DICT), num_ports))

    def _spawn_collectors(self, sw_ports, host_ips):
        # Launch an asynchronous queue collector
        proc = QueueCollector(sw_ports, self.stats, self.STATS_DICT)
        proc.start()
        self.procs.append(proc)
        # Launch an asynchronous bandwidth collector
        proc = BandwidthCollector(sw_ports, self.stats, self.STATS_DICT)
        proc.start()
        self.procs.append(proc)
        # Launch an asynchronous flow collector
        proc = FlowCollector(sw_ports, host_ips, self.flow_stats)
        proc.start()
        self.procs.append(proc)

    def _set_data_checkpoints(self, conf):
        self.data = {}
        data_dir = conf["output_dir"]
        agent = conf["agent"]

        # define file name
        runtime_name = "%s/runtime_statistics.npy" % (data_dir)
        self.stats_file = open(runtime_name, 'wb+')
        self.data["reward"] = []
        self.data["actions"] = []
        self.data["stats"] = []

    def _terminate_collectors(self):
        for proc in self.procs:
            if proc is not None:
                proc.terminate()

    def _compute_deltas(self, num_ports, stats_prev, stats_now):
        for iface_index in range(num_ports):
            for delta_index, stat in enumerate(self.STATS_DICT.keys()):
                stat_index = self.STATS_DICT[stat]
                prev = stats_prev[stat_index][iface_index]
                now = stats_now[stat_index][iface_index]
                self.deltas[delta_index][iface_index] = now - prev

    def observe(self, curr_action, do_sample):
        obs = []
        # retrieve the current deltas before updating total values
        self._compute_deltas(self.num_ports, self.prev_stats, self.stats)
        self.prev_stats = self.stats.copy()
        # Create the data matrix for the agent based on the collected stats
        for index in range(self.num_ports):
            state = []
            for key in self.STATS_KEYS:
                state.append(int(self.stats[self.STATS_DICT[key]][index]))
            for key in self.DELTA_KEYS:
                state.append(int(self.deltas[self.STATS_DICT[key]][index]))
            if self.COLLECT_FLOWS:
                state.extend(self.flow_stats[index])
            # print("State %d: %s " % (index, state))
            obs.append(np.array(state))
        # Compute the reward
        reward = self.dopamin.get_reward(
            self.stats, self.deltas, curr_action)

        if (do_sample):
            # Save collected data
            self.data["stats"].append(self.stats.copy())
            self.data["reward"].append(reward)
            self.data["actions"].append(curr_action)
        return np.array(obs), reward

    def flush(self):
        print("Saving statistics...")
        np.save(self.stats_file, np.array(self.data))
        self.stats_file.flush()
        for key in self.data.keys():
            del self.data[key][:]
