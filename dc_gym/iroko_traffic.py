import os
import sys
import csv

from time import sleep


class TrafficGen():
    SUPPORTED_TRANSPORT = ["tcp", "udp"]

    def __init__(self, topo_conf, transport):
        self.name = 'TrafficGen'
        self.topo_conf = topo_conf
        self.transport = self.set_t_type(transport)
        self.server_procs = []
        self.traffic_procs = []
        self.ctrl_procs = []
        self.monitor_bw = None
        self.monitor_qlen = None

    def set_t_type(self, transport):
        if transport.lower() in self.SUPPORTED_TRANSPORT:
            return transport.lower()
        else:
            print ("Fatal: Unknown transport protocol!")
            sys.exit(1)

    def traffic_is_active(self):
        ''' Return false if any of the processes has terminated '''
        all_procs = [self.server_procs, self.traffic_procs, self.ctrl_procs]
        for proc_list in all_procs:
            if proc_list:
                for proc in proc_list:
                    poll = proc.poll()
                    if poll is not None:
                        return False
        return True

    def _start_process(self, host, cmd, out, err):
        with open(out, 'w+') as f_out, open(err, 'w+') as f_err:
            return host.popen(cmd.split(), stdout=f_out, stderr=f_err)

    def _gen_traffic(self, out_dir, input_file):
        ''' Run the traffic generator and monitor all of the interfaces '''
        print('*** Loading file\n %s\n' % input_file)
        traffic_pattern = self.parse_traffic_file(input_file)
        net = self.topo_conf.get_net()
        self.hosts = net.hosts
        if not os.path.exists(out_dir):
            print ("Result folder %s does not exist, creating..." % out_dir)
            os.makedirs(out_dir)

        # The binaries are located in the control subfolder
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # The binary of the traffic generator
        traffic_gen = base_dir + '/goben -silent'
        # The binary of the host rate limiter
        traffic_ctrl = base_dir + '/control/node_control'

        if not os.path.isfile(traffic_ctrl):
            print("The traffic controller does not exist.\n"
                  "cd control; make\n")
            exit(1)
        print('*** Starting servers\n')
        for host in self.hosts:
            out_file = "%s/%s_server" % (out_dir, host.name)
            out = out_file + ".out"
            err = out_file + ".err"
            server_cmd = traffic_gen
            s_proc = self._start_process(host, server_cmd, out, err)
            self.server_procs.append(s_proc)

        # Wait a little to let the servers initialize
        sleep(1)
        print('*** Starting load-generators\n')
        for host in self.hosts:
            iface_net = host.intfList()[0]
            ifaces_ctrl = host.intfList()[1]
            out_file = "%s/%s" % (out_dir, host.name)
            out_ctrl = out_file + "_ctrl.out"
            err_ctrl = out_file + "_ctrl.err"
            out = out_file + "_client.out"
            err = out_file + "_client.err"

            ctrl_cmd = "%s -n %s -c %s &" % (traffic_ctrl,
                                             iface_net, ifaces_ctrl)
            c_proc = self._start_process(host, ctrl_cmd, out_ctrl, err_ctrl)
            self.ctrl_procs.append(c_proc)

            for config_row in traffic_pattern:
                duration = 2147483647  # effectively infinite runtime
                if (iface_net.IP() == config_row["src"]):
                    traffic_cmd = ("%s -totalDuration %d -maxSpeed 10"
                                   " -hosts %s -passiveServer" % (
                                       traffic_gen,
                                       duration, config_row["dst"]))
                    if self.transport == "udp":
                        traffic_cmd += " -udp"
                    t_proc = self._start_process(host, traffic_cmd, out, err)
                    self.traffic_procs.append(t_proc)

    def start_traffic(self, input_file, out_dir):
        if not input_file:
            return
        print('*** Starting traffic\n')
        self._gen_traffic(out_dir, input_file)
        # wait for load controllers to initialize
        sleep(0.5)

    def parse_traffic_file(self, traffic_file):
        traffic_pattern = []
        with open(traffic_file, 'r') as tf:
            traffic_reader = csv.DictReader(tf)
            for row in traffic_reader:
                traffic_pattern.append(row)
        return traffic_pattern

    def _kill_processes(self, procs):
        for proc in procs:
            # kill process, 15 is SIGTERM
            try:
                os.kill(proc.pid, 15)
                os.kill(proc.pid, 9)
            except OSError:
                pass

    def stop_traffic(self):
        print ('')
        if (self.traffic_is_active):
            print('*** Stopping traffic processes')
            self._kill_processes(self.server_procs)
            self._kill_processes(self.traffic_procs)
            self._kill_processes(self.ctrl_procs)
            del self.server_procs[:]
            del self.traffic_procs[:]
            del self.ctrl_procs[:]
        sys.stdout.flush()
