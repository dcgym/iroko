""" Simple test suite to verify the functionality of the bandwidth
    control library. Hardcoded. """

import ctypes
import os

FILE_DIR = os.path.dirname(os.path.abspath(__file__))


class Ring(ctypes.Structure):
    pass


bw_lib = ctypes.CDLL(FILE_DIR + "/libbw_control.so")
bw_lib.init_ring.argtypes = [ctypes.c_char_p, ctypes.c_ushort, ctypes.c_uint]
bw_lib.init_ring.restype = ctypes.POINTER(Ring)
bw_lib.send_bw.argtypes = [
    ctypes.c_ulong, ctypes.POINTER(Ring), ctypes.c_ushort]
bw_lib.wait_for_reply.argtypes = [ctypes.POINTER(Ring)]
PACKET_RX_RING = 5
PACKET_TX_RING = 13
rx_ring = bw_lib.init_ring("h1-eth0".encode("ascii"), 20135, PACKET_RX_RING)
tx_ring = bw_lib.init_ring("h1-eth0".encode("ascii"), 20135, PACKET_TX_RING)
bw_lib.send_bw(50000000, tx_ring, 20130)
bw_lib.wait_for_reply(rx_ring)
bw_lib.teardown_ring(rx_ring)
bw_lib.teardown_ring(tx_ring)
