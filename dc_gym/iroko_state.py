from filelock import FileLock
from multiprocessing import Array
from ctypes import c_ulong, c_ubyte
import numpy as np

from dc_gym.monitor.iroko_monitor import BandwidthCollector
from dc_gym.monitor.iroko_monitor import QueueCollector
from dc_gym.monitor.iroko_monitor import FlowCollector
from dc_gym.iroko_reward import RewardFunction
from dc_gym.log import IrokoLogger
log = IrokoLogger("iroko")


def shmem_to_nparray(shmem_array, dtype):
    return np.frombuffer(shmem_array.get_obj(), dtype=dtype)


class StateManager:
    STATS_DICT = {"backlog": 0, "olimit": 1,
                  "drops": 2, "bw_rx": 3, "bw_tx": 4}
    __slots__ = ["num_ports", "deltas", "prev_stats", "stats_file",
                 "stats_keys", "data", "dopamin", "stats",
                 "flow_stats", "procs", "collect_flows", "reward_model"]

    def __init__(self, config, topo_conf):
        self.stats_keys = config["state_model"]
        self.collect_flows = config["collect_flows"]
        self.reward_model = config["reward_model"]
        self.deltas = None
        self.prev_stats = None
        self._set_data_checkpoints(config["output_dir"])
        self.num_ports = topo_conf.get_num_sw_ports()
        self._init_stats_matrices(self.num_ports, topo_conf.get_num_hosts())

    def start(self, topo_conf):
        self._spawn_collectors(topo_conf)
        self.dopamin = RewardFunction(
            topo_conf, self.reward_model, self.STATS_DICT)

    def flush_and_close(self):
        log.info("Writing collected data to disk")
        with FileLock(self.stats_file.name + ".lock"):
            try:
                self.flush()
            except Exception as e:
                log.info("Error flushing file %s" % self.stats_file.name, e)
        # self.stats_file.close()

    def terminate(self):
        self._terminate_collectors()

    def reset(self):
        # self.flush()
        pass

    def _init_stats_matrices(self, num_ports, num_hosts):
        self.stats = None
        self.flow_stats = None
        self.procs = []
        # Set up the shared stats matrix
        stats_arr_len = num_ports * len(self.STATS_DICT)
        mp_stats = Array(c_ulong, stats_arr_len)
        np_stats = shmem_to_nparray(mp_stats, np.float64)
        self.stats = np_stats.reshape((len(self.STATS_DICT), num_ports))
        # Set up the shared flow matrix
        if (self.collect_flows):
            flow_arr_len = num_ports * num_hosts * 2
            mp_flows = Array(c_ubyte, flow_arr_len)
            np_flows = shmem_to_nparray(mp_flows, np.uint8)
            self.flow_stats = np_flows.reshape((num_ports, 2, num_hosts))
        # Save the initialized stats matrix to compute deltas
        self.prev_stats = self.stats.copy()
        self.deltas = np.zeros(shape=(len(self.STATS_DICT), num_ports))

    def _spawn_collectors(self, topo_conf):
        sw_ports = topo_conf.get_sw_ports()
        host_ports = topo_conf.get_host_ports()
        host_ips = topo_conf.host_ips.values()
        # Launch an asynchronous queue collector
        proc = QueueCollector(
            sw_ports, self.stats, self.STATS_DICT, topo_conf.max_queue)
        proc.start()
        self.procs.append(proc)
        # Launch an asynchronous bandwidth collector
        proc = BandwidthCollector(
            host_ports, self.stats, self.STATS_DICT, topo_conf.max_bps)
        proc.start()
        self.procs.append(proc)
        # Launch an asynchronous flow collector
        if (self.collect_flows):
            proc = FlowCollector(sw_ports, host_ips, self.flow_stats)
            proc.start()
            self.procs.append(proc)

    def _set_data_checkpoints(self, data_dir):
        self.data = {}
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
                    state.append(self.deltas[self.STATS_DICT[key[2:]]][index])
                else:
                    state.append(self.stats[self.STATS_DICT[key]][index])
            if self.collect_flows:
                state.extend(self.flow_stats[index])
            obs.append(np.array(state))
        # Compute the reward
        reward = self.dopamin.get_reward(
            self.stats, self.deltas, curr_action)

        if (do_sample):
            # Save collected data
            self.data["stats"].append(self.stats.copy())
            self.data["reward"].append(reward)
            self.data["actions"].append(curr_action.copy())
        return np.array(obs), reward

    def flush(self):
        log.info("Saving statistics...")
        if self.data["reward"]:
            np.save(self.stats_file, np.array(self.data))
            self.stats_file.flush()
            for key in self.data.keys():
                del self.data[key][:]
