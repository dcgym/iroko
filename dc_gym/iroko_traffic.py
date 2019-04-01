import os
import sys
import csv
from subprocess import Popen as popen
from time import sleep


# The binaries are located in the control subfolder
FILE_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_traffic_file(traffic_file):
    if not os.path.isfile(traffic_file):
        print("The input traffic pattern does not exist.")
        return None
    traffic_pattern = []
    with open(traffic_file, 'r') as tf:
        traffic_reader = csv.DictReader(tf)
        for row in traffic_reader:
            traffic_pattern.append(row)
    return traffic_pattern


def start_process(cmd, host=None, out_file="proc"):
    out = out_file + ".out"
    err = out_file + ".err"
    with open(out, 'w+') as f_out, open(err, 'w+') as f_err:
        if host is not None:
            return host.popen(cmd.split(), stdout=f_out, stderr=f_err)
        return popen(cmd.split(), stdout=f_out, stderr=f_err)


def kill_processes(procs):
    for proc in procs:
        # kill process, 15 is SIGTERM, 9 is SIGKILL
        try:
            os.kill(proc.pid, 15)
            # os.kill(proc.pid, 9)
        except OSError:
            pass


class TrafficGen():
    SUPPORTED_TRANSPORT = ["tcp", "udp"]

    def __init__(self, topo_conf, transport):
        self.name = 'TrafficGen'
        self.topo_conf = topo_conf
        self.procs = []
        self._set_t_type(transport)

    def _set_t_type(self, transport):
        if transport.lower() in self.SUPPORTED_TRANSPORT:
            self.transport = transport.lower()
        else:
            print("Fatal: Unknown transport protocol %s!" % transport.lower())
            print("Supported protocols are: ")
            for transport in self.SUPPORTED_TRANSPORT:
                print(transport)
            exit(1)

    def traffic_is_active(self):
        ''' Return false if any of the processes has terminated '''
        for proc in self.procs:
            poll = proc.poll()
            if poll is not None:
                return False
        return True

    def _start_servers(self, hosts, traffic_gen, out_dir):
        print('*** Starting servers')
        for host in hosts:
            out_file = "%s/%s_server" % (out_dir, host.name)
            server_cmd = traffic_gen
            s_proc = start_process(server_cmd, host, out_file)
            self.procs.append(s_proc)

    def _start_controllers(self, hosts, out_dir):
        # The binary of the host rate limiter
        traffic_ctrl = FILE_DIR + '/control/node_control'
        if not os.path.isfile(traffic_ctrl):
            print("The traffic controller does not exist.\n"
                  "Run the install.sh script to compile it.")
            kill_processes(self.procs)
            exit(1)
        print('*** Starting controllers')
        for host in hosts:
            iface_net = host.intfList()[0]
            ifaces_ctrl = host.intfList()[1]
            out_file = "%s/%s_ctrl" % (out_dir, host.name)
            ctrl_cmd = "%s " % traffic_ctrl
            ctrl_cmd += "-n %s " % iface_net
            ctrl_cmd += "-c %s " % ifaces_ctrl
            ctrl_cmd += "-r %d " % self.topo_conf.conf["max_capacity"]
            c_proc = start_process(ctrl_cmd, host, out_file)
            self.procs.append(c_proc)

    def _start_client(self, traffic_gen, host, out_dir, dst_hosts):
        if not dst_hosts:
            return
        dst_string = ""
        for dst in dst_hosts:
            dst_string += "%s," % dst
        dst_string = dst_string[:len(dst_string) - 1]
        out_file = "%s/%s_client" % (out_dir, host.name)
        max_rate = self.topo_conf.conf["max_capacity"] / 1e6
        # start the actual client
        traffic_cmd = "%s " % traffic_gen
        traffic_cmd += "-totalDuration %s " % 2147483647  # infinite runtime
        traffic_cmd += "-hosts %s " % dst_string
        traffic_cmd += "-maxSpeed %d " % max_rate
        traffic_cmd += "-passiveServer "
        traffic_cmd += "-csv %s/ping-%%d-%%s.csv " % out_dir
        if self.transport == "udp":
            traffic_cmd += "-udp "
        t_proc = start_process(traffic_cmd, host, out_file)
        self.procs.append(t_proc)

    def _start_pkt_capture(self, out_dir):
        # start a tcpdump capture process
        dmp_file = "%s/pkt_snapshot.pcap" % (out_dir)
        dmp_cmd = "tshark "
        for host_iface in self.topo_conf.host_ctrl_map:
            dmp_cmd += "-i %s " % host_iface
        dmp_cmd += "-w %s " % dmp_file
        dmp_cmd += "-f %s " % self.transport    # filter transport protocol
        dmp_cmd += "-b duration:300 "           # reset capture file after 300s
        dmp_cmd += "-b filesize:%d " % 10e5     # reset capture file after 1GB
        dmp_cmd += "-b files:1 "                # only write one capture file
        dmp_cmd += "-B 500 "                    # mb size of the packet buffer
        dmp_cmd += "-q "                        # do not print to stdout
        dmp_cmd += "-n "                        # do not resolve hosts
        dmp_cmd += "-F pcapng "                # format of the capture file
        dmp_proc = start_process(dmp_cmd, host=None, out_file=dmp_file)
        self.procs.append(dmp_proc)

    def _start_generators(self, hosts, input_file, traffic_gen, out_dir):
        print('*** Loading file:\n%s' % input_file)
        if not os.path.basename(input_file) == "all":
            traffic_pattern = parse_traffic_file(input_file)
            if traffic_pattern is None:
                kill_processes(self.procs)
                exit(1)
        print('*** Starting load-generators')
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

    def start_traffic(self, input_file, out_dir):
        ''' Run the traffic generator and monitor all of the interfaces '''
        if not input_file:
            return
        print('*** Starting traffic')
        if not os.path.exists(out_dir):
            print("Result folder %s does not exist, creating..." % out_dir)
            os.makedirs(out_dir)

        hosts = self.topo_conf.get_net().hosts
        # The binary of the traffic generator
        traffic_gen = FILE_DIR + '/goben'
        if not os.path.isfile(traffic_gen):
            print("The traffic generator does not exist.\n"
                  "Run the install.sh script with the --goben"
                  " option to compile it.\n")
            exit(1)
        # Suppress ouput of the traffic generators
        traffic_gen += " -silent "
        self._start_servers(hosts, traffic_gen, out_dir)
        self._start_controllers(hosts, out_dir)
        self._start_generators(hosts, input_file, traffic_gen, out_dir)
        # self._start_pkt_capture(out_dir)
        # wait for load controllers to initialize
        sleep(0.5)

    def stop_traffic(self):
        print('')
        if self.traffic_is_active:
            print('*** Stopping traffic processes')
            kill_processes(self.procs)
            del self.procs[:]
        sys.stdout.flush()
