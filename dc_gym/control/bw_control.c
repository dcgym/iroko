#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <net/if.h>

#include "raw_udp_socket.h"

static sig_atomic_t sigint = 0;
static struct sigaction prev_handler;
static uint16_t src_port;
typedef void (*sighandler_t)(int);

void fill_frame(uint8_t *ether_frame) {

    struct ethhdr *eth_hdr = (struct ethhdr *)((uint8_t *)ether_frame);
    struct iphdr *ip_hdr = (struct iphdr *)((uint8_t *)eth_hdr + ETH_HLEN);
    struct udphdr *udp_hdr = (struct udphdr *)((uint8_t *) ip_hdr + IP_HDRLEN);

    uint8_t src_mac[ETH_ALEN] = { 0xa0, 0x36, 0x9f, 0x45, 0xd8, 0x74 };
    uint8_t dst_mac[ETH_ALEN] = { 0xa0, 0x36, 0x9f, 0x45, 0xd8, 0x75 };

    // Destination and Source MAC addresses
    memcpy (eth_hdr->h_source, &src_mac, ETH_ALEN);
    memcpy (eth_hdr->h_dest, &dst_mac, ETH_ALEN);
    // Next is ethernet type code (ETH_P_IPV6 for IPv6).
    // http://www.iana.org/assignments/ethernet-numbers
    eth_hdr->h_proto = htons(ETH_P_IP);

    //Fill in the IP Header
    ip_hdr->ihl = 5;
    ip_hdr->version = 4;
    ip_hdr->tos = 0;
    ip_hdr->tot_len = IP_HDRLEN + UDP_HDRLEN;
    ip_hdr->id = htonl (54321);    //Id of this packet
    ip_hdr->frag_off = 0;
    ip_hdr->ttl = 255;
    ip_hdr->protocol = IPPROTO_UDP;
    ip_hdr->check = 0;     //Set to 0 before calculating checksum
    ip_hdr->saddr = htonl(INADDR_LOOPBACK);
    ip_hdr->daddr = htonl(INADDR_LOOPBACK);
    udp_hdr->source = htons(src_port);
}

int send_bw(uint32_t allocation, struct ring *ring_tx, uint16_t dst_port) {
    uint8_t ether_frame[100];
    fill_frame(ether_frame);
    struct ethhdr *eth_hdr = (struct ethhdr *)ether_frame;
    struct iphdr *ip_hdr = (struct iphdr *)((uint8_t *)eth_hdr + ETH_HLEN);
    struct udphdr *udp_hdr = (struct udphdr *)((uint8_t *) ip_hdr + IP_HDRLEN);
    // Length of UDP datagram (16 bits): UDP header + UDP data
    udp_hdr->len = htons (UDP_HDRLEN + sizeof(uint32_t));
    // Static UDP checksum
    udp_hdr->check = 0xFFAA;
    udp_hdr->dest = htons(dst_port);
    memcpy (ether_frame + HDRS_LEN, &allocation, sizeof(uint32_t));
    int pkt_len = HDRS_LEN + sizeof(uint32_t);
    return send_pkt(ring_tx, ether_frame, pkt_len);
}

#ifdef PACKET_MMAPV2
int walk_ring(struct ring *ring_rx) {
    char ifbuffer[IF_NAMESIZE];
    char *ifname;
    while (likely(!sigint)) {
        struct tpacket2_hdr *hdr = ring_rx->rd[ring_rx->p_offset].iov_base;
        if (((hdr->tp_status & TP_STATUS_USER) == TP_STATUS_USER) == 0) {
            poll(&ring_rx->pfd, 1, -1);
            ifname = if_indextoname(ring_rx->ll.sll_ifindex, ifbuffer);
            if (!ifname)
                RETURN_ERROR(EXIT_FAILURE, "receive_packet");
            continue;
        }
        hdr->tp_status = TP_STATUS_KERNEL;
        ring_rx->p_offset = (ring_rx->p_offset + 1) % ring_rx->rd_num;
        break;
    }
    return EXIT_SUCCESS;
}
#else
void walk_block(struct block_desc *pbd, const int ring_offset) {
    int num_pkts = pbd->h1.num_pkts, i;
    struct tpacket3_hdr *ppd;

    ppd = (struct tpacket3_hdr *) ((uint8_t *) pbd +
                       pbd->h1.offset_to_first_pkt);
    for (i = 0; i < num_pkts; ++i) {
        ppd = (struct tpacket3_hdr *) ((uint8_t *) ppd +
                           ppd->tp_next_offset);
    }
}

void flush_block(struct block_desc *pbd) {
    pbd->h1.block_status = TP_STATUS_KERNEL;
}

void walk_ring(struct ring *ring_rx) {
    struct block_desc *pbd;
    while (likely(!sigint)) {
        pbd = (struct block_desc *) ring_rx->rd[ring_rx->p_offset].iov_base;

        if ((pbd->h1.block_status & TP_STATUS_USER) == 0) {
            poll(&ring_rx->pfd, 1, -1);
            continue;
        }
        walk_block(pbd, ring_rx->p_offset);
        flush_block(pbd);
        ring_rx->p_offset = (ring_rx->p_offset + 1) % 256;
        break;
    }
}
#endif


void sighandler(int num) {
    sigint = 1;
}

void wait_for_reply(struct ring *ring_rx) {
    // Replace the signal handler with the internal C signal handler.
    signal(SIGINT, sighandler);
    // Wait for a packet.
    walk_ring(ring_rx);
    // We are done, restore the original handler.
    sigaction(SIGINT, &prev_handler, NULL );
    // If we stopped because of an interrupt raise another one for Python.
    if (sigint)
        raise(SIGINT);
}


struct ring *init_ring(const char *iface, uint16_t filter_port, int ring_type) {
    // We save the current active signal handler
    sigaction(SIGINT, NULL, &prev_handler);

    struct ring *ring = init_raw_backend(iface, filter_port, ring_type);
    if (ring_type == PACKET_RX_RING) {
        memset(&ring->pfd, 0, sizeof(ring->pfd));
        ring->pfd.fd = ring->socket;
        ring->pfd.events = POLLIN | POLLERR;
        ring->pfd.revents = 0;
    }
    if (ring_type == PACKET_TX_RING)  {
        src_port = filter_port;
    }
    return ring;
}

void teardown_ring(struct ring *ring) {
    // Set up the rx and tx rings
    teardown_raw_backend(ring);
}

// int test() {
//     struct ring *ring_rx = init_ring("h1-eth0", 20135, PACKET_RX_RING);
//     struct ring *ring_tx = init_ring("h1-eth0", 20135, PACKET_TX_RING);
//     printf("SENDING PACKET\n");
//     send_bw(100, ring_tx, 12321);
//     printf("WAITING...\n");
//     wait_for_reply(ring_rx);
//     printf("WAITING DONE\n");
//     teardown_ring(ring_rx);
//     teardown_ring(ring_tx);
//     return 0;
// }