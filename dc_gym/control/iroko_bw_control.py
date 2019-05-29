import os
import ctypes
import multiprocessing
import logging
log = logging.getLogger(__name__)

FILE_DIR = os.path.dirname(os.path.abspath(__file__))

SRC_PORT = 20135
DST_PORT = 20130
PACKET_RX_RING = 5
PACKET_TX_RING = 13


class Ring(ctypes.Structure):
    pass


class BandwidthController(multiprocessing.Process):
    __slots__ = ["tx_rate", "active_rate", "max_rate", "name", "host_ctrl_map",
                 "ring_list", "bw_lib", "kill"]

    def __init__(self, host_ctrl_map, tx_rate, active_rate, max_rate):
        self.name = "PolicyEnforcer"
        multiprocessing.Process.__init__(self)
        self.host_ctrl_map = host_ctrl_map
        self.tx_rate = tx_rate
        self.active_rate = active_rate
        self.max_rate = max_rate
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

    def stop(self):
        log.info("%s: Received termination signal! Exiting.." % self.name)
        self.kill.set()

    def close(self):
        self.stop()

    def _clean(self):
        pass

    def init_backend(self):
        bw_lib = ctypes.CDLL(FILE_DIR + "/libbw_control.so")
        bw_lib.init_ring.argtypes = [
            ctypes.c_char_p, ctypes.c_ushort, ctypes.c_uint]
        bw_lib.init_ring.restype = ctypes.POINTER(Ring)
        bw_lib.send_bw.argtypes = [
            ctypes.c_ulong, ctypes.POINTER(Ring), ctypes.c_ushort]
        bw_lib.send_bw.restype = ctypes.c_int
        bw_lib.wait_for_reply.argtypes = [ctypes.POINTER(Ring)]
        return bw_lib

    def init_transmissions_rings(self, host_ctrl_map):
        ring_list = {}
        for sw_iface, ctrl_iface in host_ctrl_map.items():
            ring_list[sw_iface] = {}
            rx_ring = self.bw_lib.init_ring(
                ctrl_iface.encode("ascii"), SRC_PORT, PACKET_RX_RING)
            tx_ring = self.bw_lib.init_ring(
                ctrl_iface.encode("ascii"), SRC_PORT, PACKET_TX_RING)
            ring_list[sw_iface]["rx"] = rx_ring
            ring_list[sw_iface]["tx"] = tx_ring
        return ring_list

    def destroy_transmissions_rings(self):
        for ring_pair in self.ring_list.values():
            self.bw_lib.teardown_ring(ring_pair["rx"])
            self.bw_lib.teardown_ring(ring_pair["tx"])

    def send_cntrl_pckt(self, iface, tx_rate):
        # Get the tx ring to transmit a packet
        tx_ring = self.ring_list[iface]["tx"]
        full_rate = tx_rate * self.max_rate
        ret = self.bw_lib.send_bw(int(full_rate), tx_ring, DST_PORT)
        return ret

    def await_response(self, iface):
        rx_ring = self.ring_list[iface]["rx"]
        # we do not care about payload
        # we only care about packets that pass the bpf filter
        self.bw_lib.wait_for_reply(rx_ring)

    def broadcast_bw(self):
        for index, ctrl_iface in enumerate(self.host_ctrl_map):
            if self.send_cntrl_pckt(ctrl_iface, self.active_rate[index]) != 0:
                log.error("Could not send packet!")
                self.kill.set()
                return
        for ctrl_iface in self.host_ctrl_map.keys():
            self.await_response(ctrl_iface)
        # update the active rate
        self.active_rate[:] = self.tx_rate
