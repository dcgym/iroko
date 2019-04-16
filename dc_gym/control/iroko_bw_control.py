import os
import ctypes
import gevent
import multiprocessing
import time
from dc_gym.log import IrokoLogger
log = IrokoLogger("iroko")

FILE_DIR = os.path.dirname(os.path.abspath(__file__))


class Ring(ctypes.Structure):
    pass


class BandwidthController(multiprocessing.Process):
    SRC_PORT = 20135
    DST_PORT = 20130
    PACKET_RX_RING = 5
    PACKET_TX_RING = 13

    def __init__(self, host_ctrl_map, txrate):
        multiprocessing.Process.__init__(self)
        self.host_ctrl_map = host_ctrl_map
        self.name = 'PolicyEnforcer'
        self.txrate = txrate
        # self.sock_map = self.bind_sockets(host_ctrl_map)
        self.bw_lib = self.init_backend()
        self.ring_list = self.init_transmissions_rings(host_ctrl_map)
        self.kill = multiprocessing.Event()

    def run(self):
        while not self.kill.is_set():
            try:
                self.broadcast_bw()
            except KeyboardInterrupt:
                log.error("%s: Caught Interrupt! Exiting..." % self.name)
                self.kill.set()
        self._clean()

    def terminate(self):
        log.info("%s: Received termination signal! Exiting.." % self.name)
        self.kill.set()

    def _clean(self):
        pass

    def init_backend(self):
        bw_lib = ctypes.CDLL(FILE_DIR + '/libbw_control.so')
        bw_lib.init_ring.argtypes = [
            ctypes.c_char_p, ctypes.c_ushort, ctypes.c_uint]
        bw_lib.init_ring.restype = ctypes.POINTER(Ring)
        bw_lib.send_bw_allocation.argtypes = [
            ctypes.c_ulong, ctypes.POINTER(Ring), ctypes.c_ushort]
        bw_lib.wait_for_reply.argtypes = [ctypes.POINTER(Ring)]
        return bw_lib

    def init_transmissions_rings(self, host_ctrl_map):
        ring_list = {}
        for sw_iface, ctrl_iface in host_ctrl_map.items():
            ring_list[sw_iface] = {}
            rx_ring = self.bw_lib.init_ring(
                ctrl_iface.encode('ascii'), self.SRC_PORT,
                self.PACKET_RX_RING)
            tx_ring = self.bw_lib.init_ring(
                ctrl_iface.encode('ascii'), self.SRC_PORT,
                self.PACKET_TX_RING)
            ring_list[sw_iface]["rx"] = rx_ring
            ring_list[sw_iface]["tx"] = tx_ring
        return ring_list

    def destroy_transmissions_rings(self):
        for ring_pair in self.ring_list.values():
            self.bw_lib.teardown_ring(ring_pair["rx"])
            self.bw_lib.teardown_ring(ring_pair["tx"])

    def send_cntrl_pckt(self, iface, txrate):
        # Get the tx ring to transmit a packet
        tx_ring = self.ring_list[iface]["tx"]
        self.bw_lib.send_bw_allocation(int(txrate), tx_ring, self.DST_PORT)

    def await_response(self, iface):
        rx_ring = self.ring_list[iface]["rx"]
        # we do not care about payload
        # we only care about packets that pass the bpf filter
        self.bw_lib.wait_for_reply(rx_ring)

    def broadcast_bw(self):
        for index, ctrl_iface in enumerate(self.host_ctrl_map):
            self.send_cntrl_pckt(ctrl_iface, self.txrate[index])
        for ctrl_iface in self.host_ctrl_map.keys():
            self.await_response(ctrl_iface)
        time.sleep(0.001)


# small script to test the functionality of the bw control operations
if __name__ == '__main__':
    test_list = {"test": "c0-eth0", "fest": "c0-eth1",
                 "nest": "c0-eth2", "quest": "c0-eth3"}
    ic = BandwidthController("Iroko", test_list)
    threads = []
    for iface in test_list.keys():
        threads.append(gevent.spawn(ic.await_response, iface))
        ic.send_cntrl_pckt(iface, 20000)
    gevent.joinall(threads)
