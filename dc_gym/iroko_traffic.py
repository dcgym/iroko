import os
import sys
import csv

from time import sleep

# The binaries are located in the control subfolder
FILE_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_traffic_file(traffic_file):
    traffic_pattern = []
    with open(traffic_file, 'r') as tf:
        traffic_reader = csv.DictReader(tf)
        for row in traffic_reader:
            traffic_pattern.append(row)
    return traffic_pattern


def start_process(host, cmd, out_file):
    out = out_file + ".out"
    err = out_file + ".err"
    with open(out, 'w+') as f_out, open(err, 'w+') as f_err:
        return host.popen(cmd.split(), stdout=f_out, stderr=f_err)


def kill_processes(procs):
    for proc in procs:
        # kill process, 15 is SIGTERM
        try:
            os.kill(proc.pid, 15)
            os.kill(proc.pid, 9)
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
            s_proc = start_process(host, server_cmd, out_file)
            self.procs.append(s_proc)

    def _start_controllers(self, hosts, out_dir):
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
            ctrl_cmd = "%s -n %s -c %s &" % (traffic_ctrl,
                                             iface_net, ifaces_ctrl)
            c_proc = start_process(host, ctrl_cmd, out_file)
            self.procs.append(c_proc)

    def _start_generators(self, hosts, input_file, traffic_gen, out_dir):
        print('*** Loading file:\n%s' % input_file)
        if not os.path.isfile(input_file):
            print("The input traffic pattern does not exist.")
            kill_processes(self.procs)
            exit(1)
        traffic_pattern = parse_traffic_file(input_file)
        duration = 2147483647  # effectively infinite runtime
        # The binary of the host rate limiter
        print('*** Starting load-generators')
        for host in hosts:
            iface_net = host.intfList()[0]
            out_file = "%s/%s_client" % (out_dir, host.name)
            dmp_file = "%s/%s_dmp" % (out_dir, host.name)
            for config_row in traffic_pattern:
                if iface_net.IP() == config_row["src"]:
                    # start a tcpdump capture process
                    dmp_file = "%s/%s.pcap" % (out_dir, host.name)
                    dmp_cmd = "tcpdump "
                    dmp_cmd += "-i %s " % iface_net
                    dmp_cmd += "-w %s " % dmp_file
                    dmp_cmd += "-G 300 "
                    dmp_cmd += "%s " % self.transport
                    dmp_proc = start_process(host, dmp_cmd, dmp_file)
                    self.procs.append(dmp_proc)

                    # start the actual client
                    traffic_cmd = "%s " % traffic_gen
                    traffic_cmd += "-totalDuration %s " % duration
                    traffic_cmd += "-hosts %s " % config_row["dst"]
                    traffic_cmd += "-passiveServer "
                    traffic_cmd += "-maxSpeed 10 "
                    if self.transport == "udp":
                        traffic_cmd += "-udp "
                    t_proc = start_process(host, traffic_cmd, out_file)
                    self.procs.append(t_proc)

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
        # wait for load controllers to initialize
        sleep(0.5)

    def stop_traffic(self):
        print('')
        if self.traffic_is_active:
            print('*** Stopping traffic processes')
            kill_processes(self.procs)
            del self.procs[:]
        sys.stdout.flush()
