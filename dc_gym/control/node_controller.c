#include <signal.h>
#include <unistd.h>
#include <net/if.h>

#include <libnl3/netlink/route/tc.h>
#include <libnl3/netlink/route/qdisc.h>
#include <libnl3/netlink/route/qdisc/netem.h>
#include <libnl3/netlink/route/qdisc/tbf.h>

#include "raw_udp_socket.h"

#define CTRL_PORT 20130
typedef struct ctrl_pckt {
    uint64_t tx_rate;
} ctrl_pckt;

static sig_atomic_t sigint = 0;
static struct rtnl_qdisc *fq_qdisc;
static struct nl_sock *qdisc_sock;

void ctrl_set_bw(void *data) {
    int err = 0;
    uint64_t tx_rate;
    ctrl_pckt *pkt;

    pkt = (ctrl_pckt *) data;
    tx_rate = pkt->tx_rate;
    // used for debugging purposes
    // int old_rate = rtnl_qdisc_tbf_get_rate (fq_qdisc);
    // fprintf(stderr,"tx_rate: %.3fmbit old %.3fmbit\n", tx_rate / 10e5, old_rate / 10e5);
    rtnl_qdisc_tbf_set_limit(fq_qdisc, tx_rate);
    rtnl_qdisc_tbf_set_rate(fq_qdisc, tx_rate/8, 15000, 0);
    err = rtnl_qdisc_add(qdisc_sock, fq_qdisc, NLM_F_REPLACE);
    if(err)
        fprintf(stderr,"qdisc_add: %s\n", nl_geterror(err));
}

void ctrl_handle(void *ppd_head, struct ring *ring_tx) {

#ifdef PACKET_MMAPV2
    struct tpacket2_hdr *ppd = (struct tpacket2_hdr *) ppd_head;
#else
    struct tpacket3_hdr *ppd = (struct tpacket3_hdr *) ppd_head;
#endif
    // Interpret rx packet headers
    struct ethhdr *eth_hdr = (struct ethhdr *)((uint8_t *) ppd + ppd->tp_mac);
    struct iphdr *ip_hdr = (struct iphdr *)((uint8_t *)eth_hdr + ETH_HLEN);
    struct udphdr *udp_hdr = (struct udphdr *)((uint8_t *) ip_hdr + IP_HDRLEN);
    uint8_t *data_rx = ((uint8_t *)eth_hdr + HDRS_LEN);
    uint16_t pkt_len = ppd->tp_snaplen;

    // set the bandwidth of the interface
    ctrl_set_bw(data_rx);

    // flip source and destination port
    uint16_t tmp_port = udp_hdr->dest;
    udp_hdr->dest = udp_hdr->source;
    udp_hdr->source = tmp_port;
    // bounce the flipped packet back
    send_pkt(ring_tx, (uint8_t *) eth_hdr, pkt_len);
}

#ifdef PACKET_MMAPV2
static void walk_ring(struct ring *ring_rx, struct ring *ring_tx) {
    memset(&ring_rx->pfd, 0, sizeof(ring_rx->pfd));
    ring_rx->pfd.fd = ring_rx->socket;
    ring_rx->pfd.events = POLLIN | POLLERR;
    ring_rx->pfd.revents = 0;
    while (likely(!sigint)) {
        struct tpacket2_hdr *hdr = ring_rx->rd[ring_rx->p_offset].iov_base;
        if (((hdr->tp_status & TP_STATUS_USER) == TP_STATUS_USER) == 0) {
            poll(&ring_rx->pfd, 1, -1);
            continue;
        }
        ctrl_handle(hdr, ring_tx);
        hdr->tp_status = TP_STATUS_KERNEL;
        ring_rx->p_offset = (ring_rx->p_offset + 1) % ring_rx->rd_num;
    }
}
#else
static void walk_block(struct block_desc *pbd, const int block_num, struct ring *ring_tx) {
    int num_pkts = pbd->h1.num_pkts, i;
    struct tpacket3_hdr *ppd;

    ppd = (struct tpacket3_hdr *) ((uint8_t *) pbd +
                       pbd->h1.offset_to_first_pkt);
    for (i = 0; i < num_pkts; ++i) {
        ctrl_handle(ppd, ring_tx);
        ppd = (struct tpacket3_hdr *) ((uint8_t *) ppd +
                           ppd->tp_next_offset);
    }
}

static void flush_block(struct block_desc *pbd) {
    pbd->h1.block_status = TP_STATUS_KERNEL;
}

static void walk_ring(struct ring *ring_rx, struct ring *ring_tx) {
    struct block_desc *pbd;
    memset(&ring_rx->pfd, 0, sizeof(ring_rx->pfd));
    ring_rx->pfd.fd = ring_rx->socket;
    ring_rx->pfd.events = POLLIN | POLLERR;
    ring_rx->pfd.revents = 0;

    while (likely(!sigint)) {
        pbd = (struct block_desc *) ring_rx->rd[ring_rx->p_offset].iov_base;

        if ((pbd->h1.block_status & TP_STATUS_USER) == 0) {
            poll(&ring_rx->pfd, 1, -1);
            continue;
        }
        walk_block(pbd, ring_rx->p_offset, ring_tx);
        flush_block(pbd);
        ring_rx->p_offset = (ring_rx->p_offset + 1) % 256;
    }
}
#endif

static void sighandler(int num) {
    sigint = 1;
}

struct rtnl_qdisc *setup_qdisc(struct nl_sock *qdisc_sock, const char *netdev){
    struct rtnl_qdisc *fq_qdisc;
    int if_index;
    int err = 0;

    // delete the old qdisc on the device
    char tc_cmd[200];
    snprintf(tc_cmd, 200, "tc qdisc del dev %s root", netdev);
    err = system(tc_cmd);
    if (err)
        perror("Problem with tc del");

    if_index = if_nametoindex(netdev);
    fq_qdisc = rtnl_qdisc_alloc();
    rtnl_tc_set_ifindex(TC_CAST(fq_qdisc), if_index);
    rtnl_tc_set_parent(TC_CAST(fq_qdisc), TC_H_ROOT);
    rtnl_tc_set_handle(TC_CAST(fq_qdisc), TC_HANDLE(1, 0));
    rtnl_tc_set_kind(TC_CAST(fq_qdisc), "tbf");
    rtnl_qdisc_tbf_set_limit(fq_qdisc, 10e6);
    rtnl_qdisc_tbf_set_rate(fq_qdisc, 10e6/8, 15000, 0);
    rtnl_qdisc_add(qdisc_sock, fq_qdisc, NLM_F_CREATE);
    return fq_qdisc;
}

void clean_qdisc(struct nl_sock *qdisc_sock, struct rtnl_qdisc *fq_qdisc) {
    rtnl_qdisc_put(fq_qdisc);
    nl_socket_free(qdisc_sock);
    nl_object_free((struct nl_object *) fq_qdisc);
}

void usage(char *prog_name){
    printf("usage: %s [args]\n", prog_name);
    printf("-n <netdev> - the interface attached to the main network\n");
    printf("-c <ctrldev>- the interface attached to the control network\n");
    exit(1);
}

int main(int argc, char **argv) {
    // process args
    char c;
    char *netdev = NULL;
    char *ctrldev = NULL;
    char *prog_name = argv[0];
    opterr = 0;
    while ((c = getopt(argc, argv, "n:c:")) != -1) {
        switch(c)
        {
            case 'n':
                netdev = optarg;
                break;
            case 'c':
                ctrldev = optarg;
                break;
            case '?':
                printf("unknown option: %c\n", optopt);
                usage(prog_name);
        }
    }
    if (!(netdev && ctrldev))
        usage(prog_name);
    signal(SIGINT, sighandler);


    // Set up the managing qdisc on the main interface
    qdisc_sock = nl_socket_alloc();
    nl_connect(qdisc_sock, NETLINK_ROUTE);
    fq_qdisc = setup_qdisc(qdisc_sock, netdev);

    // Set up the rx and tx rings
    struct ring *ring_rx = init_raw_backend(ctrldev, CTRL_PORT, PACKET_RX_RING);
    struct ring *ring_tx = init_raw_backend(ctrldev, CTRL_PORT, PACKET_TX_RING);
    // Start main loop
    walk_ring(ring_rx, ring_tx);
    // Clean up
    clean_qdisc(qdisc_sock, fq_qdisc);
    teardown_raw_backend(ring_rx);
    teardown_raw_backend(ring_tx);
    return 0;
}
