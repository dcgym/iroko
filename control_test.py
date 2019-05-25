import time
import ctypes
import os
import glob
import numpy as np
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.log import setLogLevel
from mininet.node import RemoteController
from multiprocessing import Array

from dc_gym.control.iroko_bw_control import BandwidthController
import dc_gym.utils as dc_utils


# configure logging
import logging
logging.basicConfig(format="%(levelname)s:%(message)s",
                    level=logging.INFO)
log = logging.getLogger(__name__)


class Ring(ctypes.Structure):
    pass


FILE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_PORT = 20135
DST_PORT = 20130
PACKET_RX_RING = 5
PACKET_TX_RING = 13


class TestTopo(Topo):

    def __init__(self, num_hosts=2):
        "The custom BlueBridge topo we use for testing."

        # Initialize topology
        Topo.__init__(self)

        switch = self.addSwitch('s1', failMode="standalone")
        for h in range(num_hosts):
            host = self.addHost('h%d' % (h),
                                ip="10.0.0.%d/24" % (h + 1),
                                mac='00:04:00:00:00:%02x' % h)
            self.addLink(host, switch)


def connect_controller(net, host):
    controller = RemoteController("c")
    net.addController(controller)
    # Configure host
    net.addLink(controller, host)
    # Configure controller
    ctrl_iface = "c-eth0"
    return ctrl_iface


def launch_ctrl(host, capacity):
    capacity = capacity * 1e6
    ctrl_cmd = f"{FILE_DIR}/dc_gym/control/node_control "
    ctrl_cmd += "-n %s " % host.intfList()[0]
    ctrl_cmd += "-c %s " % host.intfList()[1]
    ctrl_cmd += "-r %d " % capacity
    return dc_utils.start_process(ctrl_cmd, host)


def launch_goben_server(host):
    traffic_cmd = f"{FILE_DIR}/dc_gym/goben "
    return dc_utils.start_process(traffic_cmd, host)


def launch_goben_client(src_host, dst_host, in_rate):
    in_rate = in_rate / 1e6  # Goben operates on mbps
    # start the actual client
    traffic_cmd = f"{FILE_DIR}/dc_gym/goben --silent "
    traffic_cmd += "-totalDuration %s " % "inf"  # infinite
    traffic_cmd += "-hosts %s " % dst_host.IP()
    traffic_cmd += "-maxSpeed %d " % in_rate  # mbit
    traffic_cmd += "-passiveServer "
    traffic_cmd += "-udp "
    return dc_utils.start_process(traffic_cmd, src_host)


def init_rate_control(ctrl_iface, rate):
    # Initialize the action array shared with the control manager
    tx_rate = Array(ctypes.c_ulong, 1)
    tx_rate = dc_utils.shmem_to_nparray(tx_rate, np.int64)
    tx_rate.fill(rate)
    bw_proc = BandwidthController({"test": ctrl_iface}, tx_rate)
    bw_proc.start()
    return tx_rate, bw_proc


def adjust_rate(ctrl_iface, rate=1e6):
    log.info(f"Setting rate to {rate}")
    bw_lib = ctypes.CDLL(f"{FILE_DIR}/dc_gym/control/libbw_control.so")
    bw_lib.init_ring.argtypes = [
        ctypes.c_char_p, ctypes.c_ushort, ctypes.c_uint]
    bw_lib.init_ring.restype = ctypes.POINTER(Ring)
    bw_lib.send_bw.argtypes = [
        ctypes.c_ulong, ctypes.POINTER(Ring), ctypes.c_ushort]
    bw_lib.send_bw.restype = ctypes.c_int
    bw_lib.wait_for_reply.argtypes = [ctypes.POINTER(Ring)]
    rx_ring = bw_lib.init_ring(
        ctrl_iface.encode("ascii"), SRC_PORT,
        PACKET_RX_RING)
    tx_ring = bw_lib.init_ring(
        ctrl_iface.encode("ascii"), SRC_PORT,
        PACKET_TX_RING)
    bw_lib.send_bw(int(rate), tx_ring, DST_PORT)


def record_rate(in_rate, ctrl_rate, sleep, out_dir):
    # Convert to human readable format
    in_rate = in_rate / 1e6
    ctrl_rate = ctrl_rate / 1e3
    log.info(f"Input: {in_rate} Mbps Expected: {ctrl_rate} kbps")
    log.info(f"Waiting for {sleep} seconds...")
    out_dir = "control_test"
    out_file = f"{out_dir}/{in_rate}mbps_in_{ctrl_rate}kbps_expected"
    dc_utils.check_dir(out_dir)
    ifstat_cmd = "ifstat -b "
    ifstat_cmd += "-i s1-eth1 "  # interface to listen on
    ifstat_cmd += "-q 1 "  # measurement interval
    ifstat_cmd += "%d " % sleep  # measure how long
    return dc_utils.exec_process(ifstat_cmd, out_file=out_file)


def generate_ctrl_rates(base_rate):
    ctrl_rates = []
    ctrl_rates.extend([0.0001, 0.0005, 0.001, 0.005])
    ctrl_rates.extend([0.01, 0.05, 0.1, 0.5, 1])
    return np.array(ctrl_rates) * base_rate


def summarize(input_dir):
    with open(f"{input_dir}/summary.txt", 'w+') as summary_f:
        for out_file in glob.glob(f"{input_dir}/*.out"):
            file_name = os.path.splitext(out_file)[0]
            with open(out_file, 'r') as ifstat_file:
                summary_f.write(f"\n########## {file_name} ##########\n")
                items = ifstat_file.readlines()
                for item in items:
                    summary_f.write(f"{item}")


def main():
    in_rates = [10e6, 100e6, 1000e6]
    ctrl_rates = []
    out_dir = "control_test"
    sleep_per_test = 5  # seconds
    setLogLevel("info")
    topo = TestTopo(2)
    net = Mininet(topo=topo, controller=None)
    net.start()
    net.ping()
    hosts = net.hosts
    src_host = hosts[0]
    dst_host = hosts[1]
    ctrl_iface = connect_controller(net, src_host)
    ctrl_proc = launch_ctrl(src_host, 1)
    server_proc = launch_goben_server(dst_host)
    time.sleep(2)
    for in_rate in in_rates:
        tx_rate, bw_proc = init_rate_control(ctrl_iface, in_rate)
        ctrl_rates = generate_ctrl_rates(in_rate)
        client_proc = launch_goben_client(src_host, dst_host, in_rate)
        for ctrl_rate in ctrl_rates:
            log.info("\n#############################")
            # adjust_rate(ctrl_iface, ctrl_rate)
            tx_rate[0] = ctrl_rate
            dc_utils.start_process("tc qdisc show dev h0-eth0", src_host)
            record_rate(in_rate, ctrl_rate, sleep_per_test, out_dir)
            log.info("#############################")
        dc_utils.kill_processes([client_proc, bw_proc])
    dc_utils.kill_processes([server_proc, ctrl_proc])
    summarize(out_dir)
    net.stop()


if __name__ == '__main__':
    main()
