import os
import sys
import csv
import time

import dc_gym.utils as dc_utils
import logging
log = logging.getLogger(__name__)

# The binaries are located in the control subfolder
FILE_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_traffic_file(traffic_file):
    if not os.path.isfile(traffic_file):
        log.info("The input traffic pattern does not exist.")
        return None
    traffic_pattern = []
    with open(traffic_file, 'r') as tf:
        traffic_reader = csv.DictReader(tf)
        for row in traffic_reader:
            traffic_pattern.append(row)
    return traffic_pattern


class TrafficGen():
    name = "TrafficGen"
    SUPPORTED_TRANSPORT = ["tcp", "udp"]

    def __init__(self, net_man, transport, out_dir):
        self.net_man = net_man
        self.service_procs = []
        self.traffic_procs = []
        self._set_t_type(transport)
        self.out_dir = out_dir
        dc_utils.check_dir(out_dir)
        self._init_services()

    def start(self, input_file):
        self._start_traffic(input_file)

    def stop(self):
        self._stop_traffic()

    def close(self):
        self._stop_traffic()
        self._stop_services()

    def _set_t_type(self, transport):
        if transport.lower() in self.SUPPORTED_TRANSPORT:
            self.transport = transport.lower()
        else:
            log.info("Fatal: Unknown transport protocol %s!" %
                     transport.lower())
            log.info("Supported protocols are: ")
            for transport in self.SUPPORTED_TRANSPORT:
                log.info(transport)
            exit(1)

    def check_if_traffic_alive(self):
        """ Return false if any of the processes has terminated """
        for proc in self.traffic_procs:
            poll = proc.poll()
            if poll is None:
                return True
        return False

    def _start_servers(self, hosts, traffic_gen, out_dir):
        log.info("Starting servers")
        for host in hosts:
            out_file = "%s/%s_server" % (out_dir, host.name)
            server_cmd = traffic_gen
            s_proc = dc_utils.start_process(server_cmd, host, out_file)
            self.service_procs.append(s_proc)

    def _start_controllers(self, hosts, out_dir):
        # The binary of the host rate limiter
        traffic_ctrl = FILE_DIR + "/control/go_ctrl"
        if not os.path.isfile(traffic_ctrl):
            log.info("The traffic controller does not exist.\n"
                     "Run the install.sh script to compile it.")
            dc_utils.kill_processes(self.service_procs)
            exit(1)
        log.info("Starting controllers")
        for host in hosts:
            iface_net = host.intfList()[0]
            ifaces_ctrl = host.intfList()[1]
            out_file = "%s/%s_ctrl" % (out_dir, host.name)
            ctrl_cmd = "%s " % traffic_ctrl
            ctrl_cmd += "-n %s " % iface_net
            ctrl_cmd += "-c %s " % ifaces_ctrl
            ctrl_cmd += "-r %d " % self.net_man.topo.conf["max_capacity"]
            c_proc = dc_utils.start_process(ctrl_cmd, host, out_file)
            self.service_procs.append(c_proc)

    def _start_client(self, traffic_gen, host, out_dir, dst_hosts):
        if not dst_hosts:
            return
        dst_string = ""
        for dst in dst_hosts:
            dst_string += "%s," % dst
        dst_string = dst_string[:len(dst_string) - 1]
        out_file = "%s/%s_client" % (out_dir, host.name)
        max_rate = self.net_man.topo.conf["max_capacity"] / 1e6
        # start the actual client
        traffic_cmd = "%s " % traffic_gen
        traffic_cmd += "-totalDuration %s " % 60
        traffic_cmd += "-hosts %s " % dst_string
        traffic_cmd += "-maxSpeed %d " % max_rate
        traffic_cmd += "-passiveServer "
        # traffic_cmd += "-csv %s/ping-%%d-%%s.csv " % out_dir
        if self.transport == "udp":
            traffic_cmd += "-udp "
        t_proc = dc_utils.start_process(traffic_cmd, host, out_file)
        self.traffic_procs.append(t_proc)

    def _start_pkt_capture_tshark(self, out_dir):
        # start a tshark capture process
        dmp_file = "%s/pkt_snapshot.pcap" % (out_dir)
        dmp_cmd = "tshark "
        for host_iface in self.net_man.host_ctrl_map:
            dmp_cmd += "-i %s " % host_iface
        dmp_cmd += "-w %s " % dmp_file
        dmp_cmd += "-f %s " % self.transport  # filter transport protocol
        dmp_cmd += "-b duration:300 "       # reset pcap file after 300s
        dmp_cmd += "-b filesize:%d " % 10e5  # reset pcap file after 1GB
        dmp_cmd += "-b files:1 "            # only write one capture file
        dmp_cmd += "-B 500 "                # mb size of the packet buffer
        dmp_cmd += "-q "                    # do not log.info to stdout
        dmp_cmd += "-n "                    # do not resolve hosts
        dmp_cmd += "-F pcapng "             # format of the capture file
        dmp_proc = dc_utils.exec_process(dmp_cmd, out_file=dmp_file)
        self.service_procs.append(dmp_proc)

    def _start_pkt_capture_tcpdump(self, host, out_dir):
        # start a tcpdump capture process
        iface_net = host.intfList()[0]
        dmp_file = "%s/%s.pcap" % (out_dir, host.name)
        dmp_cmd = "tcpdump "
        dmp_cmd += "-i %s " % iface_net
        dmp_cmd += "-C 50 "  # roll over every 100 MB
        dmp_cmd += "-w %s " % dmp_file
        dmp_cmd += "-W 2 "    # rotate two files
        dmp_cmd += "%s " % self.transport  # filter for transport protocol
        dmp_cmd += "-Z root "
        dmp_cmd += "-s96 "      # Capture only headers
        dmp_proc = dc_utils.start_process(dmp_cmd, host, dmp_file)
        self.service_procs.append(dmp_proc)

    def _start_generators(self, hosts, input_file, traffic_gen, out_dir):
        log.info("Loading file: %s" % input_file)
        if not os.path.basename(input_file) == "all":
            traffic_pattern = parse_traffic_file(input_file)
            if traffic_pattern is None:
                log.error("No traffic pattern provided!")
                dc_utils.kill_processes(self.service_procs)
                exit(1)
        log.info("Starting load-generators")
        if os.path.basename(input_file) == "all":
            # generate an all-to-all pattern
            for src_host in hosts:
                dst_hosts = []
                for dst_host in hosts:
                    if src_host != dst_host:
                        dst_hosts.append(dst_host.intfList()[0].IP())
                self._start_client(traffic_gen, src_host, out_dir, dst_hosts)
        else:
            for src_host in hosts:
                host_ip = src_host.intfList()[0].IP()
                dst_hosts = []
                # generate a pattern according to the traffic matrix
                for config_row in traffic_pattern:
                    if host_ip == config_row["src"]:
                        dst_hosts.append(config_row["dst"])
                self._start_client(traffic_gen, src_host, out_dir, dst_hosts)
                # self._start_pkt_capture_tcpdump(src_host, out_dir)

    def _init_services(self):
        """ Run the servers and monitors on all the host interfaces """
        hosts = self.net_man.get_net().hosts
        # The binary of the traffic generator
        traffic_gen = FILE_DIR + "/goben"
        if not os.path.isfile(traffic_gen):
            log.info("The traffic generator does not exist.\n"
                     "Run the install.sh script with the --goben"
                     " option to compile it.")
            exit(1)
        # Suppress ouput of the traffic generators
        traffic_gen += " -silent "
        self._start_servers(hosts, traffic_gen, self.out_dir)
        self._start_controllers(hosts, self.out_dir)
        # self._start_pkt_capture(self.out_dir)
        # wait for load controllers to initialize
        time.sleep(0.5)

    def _stop_services(self):
        log.info("")
        log.info("Stopping services")
        dc_utils.kill_processes(self.service_procs)
        del self.service_procs[:]
        sys.stdout.flush()

    def _start_traffic(self, input_file):
        """ Run the traffic generators"""
        if not input_file:
            log.error("No traffic file provided!")
            exit(1)
        hosts = self.net_man.get_net().hosts
        # The binary of the traffic generator
        traffic_gen = FILE_DIR + "/goben"

        log.info("Starting traffic")
        self._start_generators(hosts, input_file, traffic_gen, self.out_dir)

    def _stop_traffic(self):
        log.info("")
        log.info("Stopping traffic processes")
        dc_utils.kill_processes(self.traffic_procs)
        del self.traffic_procs[:]
        sys.stdout.flush()
