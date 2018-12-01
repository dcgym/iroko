import socket
from scapy.all import IP
from scapy.all import UDP
from scapy.all import Ether


class BandwidthController():
    def __init__(self, name, host_ctrl_map):
        name = name
        self.host_ctrl_map = host_ctrl_map
        self.sock_map = self.bind_sockets(host_ctrl_map)
        self.etherframe = self.create_udp_header()

    def create_udp_header(self):
        ip_hdr = IP(src="172.168.5.1", dst='172.168.10.1')
        udp_hdr = UDP(sport=20135, dport=20130)
        return Ether() / ip_hdr / udp_hdr

    def ip2int(self, ip_addr):
        if ip_addr == 'localhost':
            ip_addr = '127.0.0.1'
        return [int(x) for x in ip_addr.split('.')]

    def bind_sockets(self, host_ctrl_map):
        sock_map = {}
        for sw_iface, ctrl_iface in host_ctrl_map.items():
            print("Binding socket %s" % ctrl_iface)
            sock = socket.socket(
                socket.AF_PACKET, socket.SOCK_RAW, socket.IPPROTO_UDP)
            sock.bind((ctrl_iface, 0))
            sock_map[sw_iface] = sock
        return sock_map

    def send_cntrl_pckt(self, iface, txrate):
        packet = str(self.etherframe) + str(long(txrate)).zfill(8)
        target_sock = self.sock_map[iface]
        target_sock.sendall(packet)
