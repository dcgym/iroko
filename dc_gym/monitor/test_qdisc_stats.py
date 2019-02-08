''' Simple test suite to verify the functionality of the bandwidth
    control library. Hardcoded. '''

import ctypes
import os

FILE_DIR = os.path.dirname(os.path.abspath(__file__))


class Qdisc(ctypes.Structure):
    pass


q_lib = ctypes.CDLL(FILE_DIR + '/libqdisc_stats.so')
q_lib.init_qdisc_monitor.argtypes = [ctypes.c_char_p]
q_lib.init_qdisc_monitor.restype = ctypes.POINTER(Qdisc)
qdisc = q_lib.init_qdisc_monitor("sw1-eth1")
qdisc2 = q_lib.init_qdisc_monitor("sw1-eth3")
print(q_lib.get_qdisc_backlog(qdisc))
print(q_lib.get_qdisc_drops(qdisc))
print(q_lib.get_qdisc_overlimits(qdisc))
print(q_lib.get_qdisc_packets(qdisc))
print(q_lib.get_qdisc_backlog(qdisc2))
print(q_lib.get_qdisc_drops(qdisc2))
print(q_lib.get_qdisc_overlimits(qdisc2))
print(q_lib.get_qdisc_packets(qdisc2))
q_lib.delete_qdisc_monitor(qdisc)
q_lib.delete_qdisc_monitor(qdisc2)
