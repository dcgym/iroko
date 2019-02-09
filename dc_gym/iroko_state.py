import numpy as np
from multiprocessing import Array
from ctypes import c_ulong, c_double, c_ubyte

from monitor.iroko_monitor import BandwidthCollector
from monitor.iroko_monitor import QueueCollector
from monitor.iroko_monitor import FlowCollector
from iroko_reward import RewardFunction

# REWARD_MODEL = ["action", "queue", "std_dev"]
REWARD_MODEL = ["action", "queue"]
###########################################


class StateManager():
    DELTA_KEYS = ["delta_backlog_abs"]
    BW_KEYS = []
    Q_KEYS = ["backlog"]
    COLLECT_FLOWS = True

    def __init__(self, topo_conf, config, reward_fun=REWARD_MODEL):
        self.conf = config
        self.ports = topo_conf.get_sw_ports()
        self.num_ports = len(self.ports)
        self.topo_conf = topo_conf
        self._set_feature_length()
        self._spawn_collectors(topo_conf.host_ips)
        self._set_reward(reward_fun, topo_conf)
        self._set_data_checkpoints(topo_conf)

    def terminate(self):
        self.flush()
        # self._terminate_collectors()
        self.reward_file.close()
        self.action_file.close()
        self.queue_file.close()
        self.bw_file.close()

    def reset(self):
        self.flush()

    def _set_data_checkpoints(self, topo_conf):
        data_dir = self.conf["output_dir"]
        agent = self.conf["agent"]
        # define file names
        reward_name = "%s/reward_per_step_%s.npy" % (data_dir, agent)
        action_name = "%s/action_per_step_by_port_%s.npy" % (data_dir, agent)
        queue_name = "%s/queues_per_step_by_port_%s.npy" % (data_dir, agent)
        bw_name = "%s/bandwidths_per_step_by_port_%s.npy" % (data_dir, agent)
        self.reward_file = open(reward_name, 'wb+')
        self.action_file = open(action_name, 'wb+')
        self.queue_file = open(queue_name, 'wb+')
        self.bw_file = open(bw_name, 'wb+')
        self.time_step_reward = []
        self.queues_per_port = []
        self.action_per_port = []
        self.bws_per_port = []

    def _set_feature_length(self):
        self.num_features = len(self.DELTA_KEYS)
        self.num_features += len(self.Q_KEYS) + len(self.BW_KEYS)
        if (self.COLLECT_FLOWS):
            self.num_features += len(self.topo_conf.host_ips) * 2

    def _set_reward(self, reward_fun, topo_conf):
        self.dopamin = RewardFunction(topo_conf.host_ctrl_map,
                                      self.ports,
                                      reward_fun, topo_conf.MAX_QUEUE,
                                      topo_conf.MAX_CAPACITY, self.q_dict)

    def _spawn_collectors(self, host_ips):

        # Launch an asynchronous queue collector
        self.q_dict = {"backlog": 0, "overlimits": 1,
                       "drops": 2, "rate_bps": 3, "rate_pps": 4}
        self.q_stats = Array(c_ulong, self.num_ports * len(self.q_dict))
        self.q_stats_proc = QueueCollector(
            self.ports, self.q_stats, self.q_dict)
        self.q_stats_proc.start()
        # Launch an asynchronous bandwidth collector
        self.bw_dict = {"bw_rx": 0, "bw_tx": 1}
        self.bw_stats = Array(c_double, self.num_ports * len(self.bw_dict))
        self.bw_stats_proc = BandwidthCollector(
            self.ports, self.bw_stats, self.bw_dict)
        self.bw_stats_proc.start()
        # Launch an asynchronous flow collector
        self.flow_dict = {"src": 0, "dst": 1}
        self.flow_stats = Array(
            c_ubyte, self.num_ports * len(self.flow_dict) * len(host_ips))
        self.flows_proc = FlowCollector(
            self.ports, host_ips, self.flow_stats, self.flow_dict)
        self.flows_proc.start()
        # initialize the stats matrix
        self.prev_q_stats = list(self.q_stats)

    def _terminate_collectors(self):
        if (self.q_stats_proc is not None):
            self.q_stats_proc.terminate()
        if (self.bw_stats_proc is not None):
            self.bw_stats_proc.terminate()
        if (self.flows_proc is not None):
            self.flows_proc.terminate()

    def _compute_delta(self, ports, stats_prev, stats_now):
        deltas = {}
        for index, iface in enumerate(ports):
            offset = len(self.q_dict) * index
            # bws_rx_prev = stats_prev[iface]["bws_rx"]
            # bws_tx_prev = stats_prev[iface]["bws_tx"]
            drops_prev = stats_prev[offset + self.q_dict["drops"]]
            overlimits_prev = stats_prev[offset + self.q_dict["overlimits"]]
            queues_prev = stats_prev[offset + self.q_dict["backlog"]]

            # bws_rx_now = stats_now[offset + self.q_dict["bws_rx"]]
            # bws_tx_now = stats_now[offset + self.q_dict["bws_tx"]]
            drops_now = stats_now[offset + self.q_dict["drops"]]
            overlimits_now = stats_now[offset + self.q_dict["overlimits"]]
            queues_now = stats_now[offset + self.q_dict["backlog"]]

            deltas[iface] = {}
            # if bws_rx_prev <= bws_rx_now:
            #     deltas[iface]["delta_rx"] = 1
            # else:
            #     deltas[iface]["delta_rx"] = 0

            # if bws_tx_prev <= bws_tx_now:
            #     deltas[iface]["delta_tx"] = 1
            # else:
            #     deltas[iface]["delta_tx"] = 0

            if drops_prev < drops_now:
                deltas[iface]["delta_d"] = 0
            else:
                deltas[iface]["delta_d"] = 1

            if overlimits_prev < overlimits_now:
                deltas[iface]["delta_ov"] = 0
            else:
                deltas[iface]["delta_ov"] = 1

            if queues_prev < queues_now:
                deltas[iface]["delta_q"] = 1
            elif queues_prev > queues_now:
                deltas[iface]["delta_q"] = -1
            else:
                deltas["delta_q"] = 0
            deltas[iface]["delta_backlog_abs"] = queues_now - queues_prev
            # deltas[iface]["delta_rx_abs"] = bws_rx_now - bws_rx_prev
            # deltas[iface]["delta_tx_abs"] = bws_tx_now - bws_tx_prev
        return deltas

    def collect(self):
        obs = np.zeros((self.num_ports, self.num_features))

        # retrieve the current deltas before updating total values
        delta_vector = self._compute_delta(
            self.ports, self.prev_q_stats, self.q_stats)
        self.prev_q_stats = list(self.q_stats)
        # Create the data matrix for the agent based on the collected stats
        for index, iface in enumerate(self.ports):
            state = []
            deltas = delta_vector[iface]
            for key in self.DELTA_KEYS:
                state.append(deltas[key])
            for key in self.Q_KEYS:
                offset = len(self.q_dict) * index
                state.append(int(self.q_stats[offset + self.q_dict[key]]))
            for key in self.BW_KEYS:
                offset = len(self.bw_dict) * index
                state.append(float(self.bw_stats[offset + self.bw_dict[key]]))
            if self.COLLECT_FLOWS:
                flow_len = len(self.topo_conf.host_ips) * len(self.flow_dict)
                offset = flow_len * index
                state.extend(self.flow_stats[offset:(offset + flow_len)])
            # print("State %s: %s " % (iface, state))
            obs[index] = np.array(state)
        # Save collected data
        self.queues_per_port.append(list(self.q_stats))
        self.bws_per_port.append(list(self.bw_stats))
        return obs

    def compute_reward(self, curr_action):
        # Compute the reward
        reward = self.dopamin.get_reward(
            (self.q_stats, self.bw_stats), curr_action)
        self.action_per_port.append(curr_action)
        self.time_step_reward.append(reward)
        return reward

    def flush(self):
        print ("Saving statistics...")
        np.save(self.reward_file, self.time_step_reward)
        np.save(self.action_file, self.action_per_port)
        np.save(self.queue_file, self.queues_per_port)
        np.save(self.bw_file, self.bws_per_port)
        self.reward_file.flush()
        self.action_file.flush()
        self.queue_file.flush()
        self.bw_file.flush()
        del self.time_step_reward[:]
        del self.action_per_port[:]
        del self.queues_per_port[:]
        del self.bws_per_port[:]
