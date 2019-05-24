#include <signal.h>
#include <unistd.h>

#include "ctrl_common.h"

#define CTRL_PORT 20130
#define MTU 1500

static sig_atomic_t sigint = 0;
double MAX_RATE = 1e9;



void handle_pkt(void *ppd_head, struct ring *ring_tx, HANDLE_TYPE *ctrl_handle) {

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
    ctrl_set_bw(data_rx, ctrl_handle);

    // flip source and destination port
    uint16_t tmp_port = udp_hdr->dest;
    udp_hdr->dest = udp_hdr->source;
    udp_hdr->source = tmp_port;
    // bounce the flipped packet back
    send_pkt(ring_tx, (uint8_t *) eth_hdr, pkt_len);
}

#ifdef PACKET_MMAPV2
static void walk_ring(struct ring *ring_rx, struct ring *ring_tx, HANDLE_TYPE *ctrl_handle) {
    memset(&ring_rx->pfd, 0, sizeof(ring_rx->pfd));
    ring_rx->pfd.fd = ring_rx->socket;
    ring_rx->pfd.events = POLLIN | POLLERR;
    ring_rx->pfd.revents = 0;
    while (likely(!sigint)) {
        struct tpacket2_hdr *hdr = ring_rx->rd[ring_rx->p_offset].iov_base;
        if (((hdr->tp_status & TP_STATUS_USER) == TP_STATUS_USER) == 0) {
            poll(&ring_rx->pfd, 1, -1);
            if (ring_rx->pfd.revents & POLLERR) {
                perror("Error while polling");
                exit(1);
            }
            continue;
        }
        handle_pkt(hdr, ring_tx, ctrl_handle);
        hdr->tp_status = TP_STATUS_KERNEL;
        ring_rx->p_offset = (ring_rx->p_offset + 1) % ring_rx->rd_num;
    }
}
#else
static void walk_block(struct block_desc *pbd, const int block_num, struct ring *ring_tx, HANDLE_TYPE *ctrl_handle) {
    int num_pkts = pbd->h1.num_pkts, i;
    struct tpacket3_hdr *ppd;

    ppd = (struct tpacket3_hdr *) ((uint8_t *) pbd +
                       pbd->h1.offset_to_first_pkt);
    for (i = 0; i < num_pkts; ++i) {
        handle_pkt(ppd, ring_tx, ctrl_handle);
        ppd = (struct tpacket3_hdr *) ((uint8_t *) ppd +
                           ppd->tp_next_offset);
    }
}

static void flush_block(struct block_desc *pbd) {
    pbd->h1.block_status = TP_STATUS_KERNEL;
}

static void walk_ring(struct ring *ring_rx, struct ring *ring_tx, HANDLE_TYPE *ctrl_handle) {
    struct block_desc *pbd;
    memset(&ring_rx->pfd, 0, sizeof(ring_rx->pfd));
    ring_rx->pfd.fd = ring_rx->socket;
    ring_rx->pfd.events = POLLIN | POLLERR;
    ring_rx->pfd.revents = 0;

    while (likely(!sigint)) {
        pbd = (struct block_desc *) ring_rx->rd[ring_rx->p_offset].iov_base;

        if ((pbd->h1.block_status & TP_STATUS_USER) == 0) {
            printf("waiting for packet\n");
            poll(&ring_rx->pfd, 1, -1);
            if (ring_rx->pfd.revents & POLLERR) {
                perror("poll");
                exit(1);
            }
            continue;
        }
        walk_block(pbd, ring_rx->p_offset, ring_tx, ctrl_handle);
        flush_block(pbd);
        ring_rx->p_offset = (ring_rx->p_offset + 1) % 256;
    }
}
#endif

static void sighandler(int num) {
    sigint = 1;
}

int delete_qdisc(char *netdev) {
    char tc_cmd[200];
    int err = 0;
    // delete the old qdisc on the device
    snprintf(tc_cmd, 200, "tc qdisc del dev %s root", netdev);
    err = system(tc_cmd);
    if (err)
        RETURN_ERROR(EXIT_FAILURE, "Problem with tc qdisc del");
    return EXIT_SUCCESS;
}

void usage(char *prog_name){
    printf("usage: %s [args]\n", prog_name);
    printf("-n <netdev> - the interface attached to the main network\n");
    printf("-c <ctrldev>- the interface attached to the control network\n");
    printf("-r <rate> - the initial rate of the controlling qdisc in bits\n");
    exit(1);
}

int main(int argc, char **argv) {
    // process args
    char c;
    char *ctrldev = NULL;
    char *netdev = NULL;
    HANDLE_TYPE *ctrl_handle = NULL;
    char *prog_name = argv[0];
    opterr = 0;
    while ((c = getopt(argc, argv, "n:c:r:")) != -1) {
        switch(c)
        {
            case 'n':
                netdev = optarg;
                break;
            case 'c':
                ctrldev = optarg;
                break;
            case 'r':
                MAX_RATE = atoll(optarg);
                break;
            case '?':
                printf("unknown option: %c\n", optopt);
                usage(prog_name);
        }
    }
    // Control and transmission devices are necessary
    if (!(netdev && ctrldev))
        usage(prog_name);

    signal(SIGINT, sighandler);

    ctrl_handle = setup_qdisc(netdev, MAX_RATE);

    // Set up the rx and tx rings
    struct ring *ring_rx = init_raw_backend(ctrldev, CTRL_PORT, PACKET_RX_RING);
    struct ring *ring_tx = init_raw_backend(ctrldev, CTRL_PORT, PACKET_TX_RING);
    // Start main loop
    walk_ring(ring_rx, ring_tx, ctrl_handle);

    // Done with the loop, clean up
    teardown_raw_backend(ring_rx);
    teardown_raw_backend(ring_tx);

    // Clean up
    clean_qdisc(ctrl_handle);
    delete_qdisc(netdev);

    return EXIT_SUCCESS;
}
