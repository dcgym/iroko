import socket
from ctypes import create_string_buffer
from struct import pack, pack_into, calcsize

''' A majority of the source code here is inspired by
https://github.com/YingquanYuan/raw_sockets '''


def checksum(data):
    '''
    Return the checksum of the given data.
    The algorithm comes from:
    http: // en.wikipedia.org / wiki / IPv4_header_checksum
    '''
    sum = 0
    # pick up 16 bits (2 WORDs) every time
    for i in range(0, len(data), 2):
        # Sum up the ordinal of each WORD with
        # network bits order (big-endian)
        if i < len(data) and (i + 1) < len(data):
            sum += (ord(data[i]) + (ord(data[i + 1]) << 8))
        elif i < len(data) and (i + 1) == len(data):
            sum += ord(data[i])
    addon_carry = (sum & 0xffff) + (sum >> 16)
    result = (~ addon_carry) & 0xffff
    # swap bytes
    result = result >> 8 | ((result & 0x00ff) << 8)
    return result


class EtherFrame():
    ''' Simple Python model for an Ethernet Frame '''
    ETH_HDR_FMT = '!6s6sH'

    def __init__(self, dest_mac='', src_mac='', tcode=0x0800):
        self.eth_dest_addr = self.mac_str_to_hex(dest_mac)
        self.eth_src_addr = self.mac_str_to_hex(src_mac)
        self.eth_tcode = tcode
        self.raw = self.prep()

    def __repr__(self):
        repr = ('EtherFrame: ' +
                '[dest_mac: %s, src_mac: %s, tcode: 0x%04x,' +
                ' len(data): %d]') \
            % (self._eth_addr(self.eth_dest_addr),
               self._eth_addr(self.eth_src_addr),
               self.eth_tcode, len(self.data))
        return repr

    def prep(self):
        eth_header = pack(self.ETH_HDR_FMT,
                          self.eth_dest_addr, self.eth_src_addr,
                          self.eth_tcode)
        return eth_header

    def _eth_addr(self, raw):
        hex = '%.2x:%.2x:%.2x:%.2x:%.2x:%.2x' \
            % (ord(raw[0]), ord(raw[1]), ord(raw[2]),
               ord(raw[3]), ord(raw[4]), ord(raw[5]))
        return hex

    def mac_str_to_hex(self, mac_address):
        """ Receives a string mac address and returns an on-the-wire
        representation of it """
        mac_octets = [int(octet, 16) for octet in mac_address.split(":")]
        return pack("B" * 6, *mac_octets)


class IPFrame:
    '''
    Simple Python model for an IP datagram
    '''

    IP_HDR_FMT = '!BBHHHBBH4s4s'

    def __init__(self, ip_src_addr, ip_dest_addr, ip_ver=4,
                 ip_ihl=5, ip_tos=0, ip_id=54321, ip_frag_off=0,
                 ip_ttl=255, ip_proto=socket.IPPROTO_UDP,
                 ip_opts=None):
        # vars for IP header
        # all IP addresses has been encoded
        self.ip_ver = ip_ver
        self.ip_ihl = ip_ihl
        self.ip_tos = ip_tos
        self.ip_tlen = 0
        self.ip_id = ip_id
        self.ip_frag_off = ip_frag_off
        self.ip_ttl = ip_ttl
        self.ip_proto = ip_proto
        self.ip_hdr_cksum = 0
        self.ip_src_addr = ip_src_addr
        self.ip_dest_addr = ip_dest_addr
        self.ip_opts = ip_opts
        self.ip_tlen = 4 * self.ip_ihl
        self.ip_hdr_buf = create_string_buffer(calcsize(self.IP_HDR_FMT))
        self.raw = self.prep()

    def __repr__(self):
        repr = ('IPDatagram: ' +
                '[ver: %d, ihl: %d, tos: %d, tlen: %d, id: %d, ' +
                ' frag_off: %d, ttl: %d, proto: %d, hdr_checksum: 0x%04x,' +
                ' src_addr: %s, dest_addr: %s, options: %s]') \
            % (self.ip_ver, self.ip_ihl, self.ip_tos, self.ip_tlen,
               self.ip_id, self.ip_frag_off, self.ip_ttl, self.ip_proto,
               self.ip_hdr_cksum, socket.inet_ntoa(self.ip_src_addr),
               socket.inet_ntoa(self.ip_dest_addr),
               'Yes' if self.ip_opts else None)
        return repr

    def prep(self):
        '''
        Pack the IPDatagram object to an IP datagram string.
        We compute the IP headers checksum with leaving the
        checksum field empty, and then pack the checksum
        into the IP headers. So that the verification of the
        header checksum could use the same checksum algorithm,
        and then simply check if the result is 0.
        '''
        ip_ver_ihl = (self.ip_ver << 4) + self.ip_ihl
        pack_into(self.IP_HDR_FMT, self.ip_hdr_buf, 0,
                  ip_ver_ihl, self.ip_tos, self.ip_tlen,
                  self.ip_id, self.ip_frag_off,
                  self.ip_ttl, self.ip_proto,
                  self.ip_hdr_cksum,
                  self.ip_src_addr, self.ip_dest_addr)

    def update(self, data_len):
        self.ip_tlen = 4 * self.ip_ihl + data_len
        pack_into('!H', self.ip_hdr_buf, calcsize(self.IP_HDR_FMT[:2]),
                  self.ip_tlen)
        # self.ip_hdr_cksum = checksum(self.ip_hdr_buf.raw)
        # pack_into('!H', self.ip_hdr_buf, calcsize(self.IP_HDR_FMT[:8]),
        #           self.ip_hdr_cksum)
        self.raw = self.ip_hdr_buf.raw


class UDPFrame:
    '''
    Simple Python model for an UDP datagram
    '''
    UDP_HDR_FMT = '!HHHH'
    UDP_HDR_LEN = 8

    def __init__(self, src_port=20135, dst_port=20130):
        # vars for IP header
        # all IP addresses has been encoded
        self.src_port = src_port
        self.dst_port = dst_port
        self.udp_hdr_buf = create_string_buffer(calcsize(self.UDP_HDR_FMT))
        self.raw = self.prep()

    def __repr__(self):
        repr = ('UDPFrame: ' + '[src port: %d, dst port: %d, udp len: %d]'
                % self.src_port, self.dst_port, self.udp_len)
        return repr

    def prep(self):
        pack_into(self.UDP_HDR_FMT, self.udp_hdr_buf, 0,
                  self.src_port, self.dst_port, self.UDP_HDR_LEN, 0)
        return self.udp_hdr_buf.raw

    def update(self, data_len):
        self.udp_len = self.UDP_HDR_LEN + data_len
        pack_into('!H', self.udp_hdr_buf, calcsize(
            self.UDP_HDR_FMT[:1]), self.udp_len)
        self.raw = self.udp_hdr_buf.raw


class BandwidthController():
    def __init__(self, name, host_ctrl_map):
        name = name
        self.host_ctrl_map = host_ctrl_map
        self.sock_map = self.bind_sockets(host_ctrl_map)
        self.init_headers()

    def init_headers(self, ip_src='172.168.5.1', ip_dst='172.168.10.1',
                     src_port=20135, dst_port=20130):
        # build ETH header
        self.eth_header = EtherFrame(dest_mac='10:7b:44:4a:7e:19',
                                     src_mac='10:7b:44:4a:7e:20')
        # build IP header
        self.ip_header = IPFrame(ip_src_addr=socket.inet_aton(ip_src),
                                 ip_dest_addr=socket.inet_aton(ip_dst))
        # build UDP header
        self.udp_header = UDPFrame(src_port, dst_port)

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
        data_len = 8
        self.ip_header.update(data_len)
        self.udp_header.update(data_len)
        target_sock = self.sock_map[iface]
        # Assemble packet
        packet = self.eth_header.raw
        packet += self.ip_header.raw
        packet += self.udp_header.raw
        packet += str(txrate).zfill(8).encode()
        target_sock.sendall(packet)
