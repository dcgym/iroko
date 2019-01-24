#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <sys/mman.h>
#include <linux/if_packet.h>
#include <linux/filter.h>
#include <unistd.h>
#include <string.h>
#include <net/if.h>
#include <poll.h>
#include <net/ethernet.h>
#include <netinet/udp.h>   //Provides declarations for udp header
#include <netinet/ip.h> //Provides declarations for ip header

#include <libnl3/netlink/route/tc.h>
#include <libnl3/netlink/route/qdisc.h>
#include <libnl3/netlink/route/qdisc/netem.h>
#include <libnl3/netlink/route/qdisc/tbf.h>

#ifndef likely
# define likely(x)      __builtin_expect(!!(x), 1)
#endif
#ifndef unlikely
# define unlikely(x)        __builtin_expect(!!(x), 0)
#endif

// (unimportant) macro for loud failure
// needs some love in the code
#define RETURN_ERROR(lvl, msg) \
  do {                    \
    perror(msg); \
    return lvl;            \
  } while(0);

#define CTRL_PORT  20130
#define CTRL_PCKT_SIZE 9450
typedef struct ctrl_pckt {
    char buf_size[20];
} ctrl_pckt;


struct ring {
    struct iovec *rd;
    uint8_t *mm_space;
    size_t mm_len, rd_len;
    struct sockaddr_ll ll;
    void (*walk)(int sock, struct ring *ring);
    int type, rd_num, flen, version;
    union {
        struct tpacket_req  req;
        struct tpacket_req3 req3;
    };
};

struct block_desc {
    uint32_t version;
    uint32_t offset_to_priv;
    struct tpacket_hdr_v1 h1;
};

static int sock_rx;
static int sock_tx;
static struct ring ring_tx;
static struct ring ring_rx;

// Super shitty hack. Do not try this at home kids.
int set_packet_filter(int sd, const char *iface, int port) {
    struct sock_fprog filter;
    int i, lineCount = 0;
    char cmd[512];
    FILE* tcpdump_output;
    sprintf(cmd, "tcpdump -i %s dst port %d and udp -ddd", iface, port);

    printf("Active Filter: %s\n",cmd );
    if ( (tcpdump_output = popen(cmd, "r")) == NULL )
        RETURN_ERROR(EXIT_FAILURE, "Cannot compile filter using tcpdump.");
    if (fscanf(tcpdump_output, "%d\n", &lineCount) < 1 )
        RETURN_ERROR(EXIT_FAILURE, "cannot read lineCount.");
    filter.filter = (struct sock_filter *)calloc(1, sizeof(struct sock_filter)*lineCount);
    filter.len = lineCount;
    for (i = 0; i < lineCount; i++) {
        if (fscanf(tcpdump_output, "%u %u %u %u\n", (unsigned int *)&(filter.filter[i].code),(unsigned int *) &(filter.filter[i].jt),(unsigned int *) &(filter.filter[i].jf), &(filter.filter[i].k)) < 4 ) {
            free(filter.filter);
            RETURN_ERROR(EXIT_FAILURE, "fscanf: error in reading");
        }
        setsockopt(sd, SOL_SOCKET, SO_ATTACH_FILTER, &filter, sizeof(filter));
    }
    pclose(tcpdump_output);
    free(filter.filter);
    return EXIT_SUCCESS;
}

static int init_socket(int ver, const char *netdev, int port) {
    int ret, sock = socket(AF_PACKET, SOCK_RAW, 0);
    if (sock == -1) {
        perror("socket");
        exit(1);
    }
    ret = set_packet_filter(sock, netdev, CTRL_PORT);
    if (ret == -1) {
        perror("filter");
        exit(1);
    }
    ret = setsockopt(sock, SOL_PACKET, PACKET_VERSION, &ver, sizeof(ver));
    if (ret == -1) {
        perror("setsockopt");
        exit(1);
    }
    return sock;
}

static void fill_ring(struct ring *ring, unsigned int blocks, int type) {
    if (type == PACKET_RX_RING) {
        ring->req3.tp_retire_blk_tov = 64;
        ring->req3.tp_sizeof_priv = 0;
        ring->req3.tp_feature_req_word = TP_FT_REQ_FILL_RXHASH;
    }
    ring->req3.tp_block_size = getpagesize() << 2;
    ring->req3.tp_frame_size = TPACKET_ALIGNMENT << 7;
    ring->req3.tp_block_nr = blocks;

    ring->req3.tp_frame_nr = ring->req3.tp_block_size /
                 ring->req3.tp_frame_size *
                 ring->req3.tp_block_nr;

    ring->mm_len = ring->req3.tp_block_size * ring->req3.tp_block_nr;
    ring->rd_num = ring->req3.tp_block_nr;
    ring->flen = ring->req3.tp_block_size;
}

static void setup_ring(int sock, struct ring *ring, int version, int type) {
    int ret = 0;
    unsigned int blocks = 256;

    ring->type = type;
    ring->version = version;
    fill_ring(ring, blocks, type);
    ret = setsockopt(sock, SOL_PACKET, type, &ring->req3,
             sizeof(ring->req3));

    if (ret == -1) {
        perror("setsockopt");
        exit(1);
    }

    ring->rd_len = ring->rd_num * sizeof(*ring->rd);
    ring->rd = malloc(ring->rd_len);
    if (ring->rd == NULL) {
        perror("malloc");
        exit(1);
    }
}

static void mmap_ring(int sock, struct ring *ring) {
    int i;

    ring->mm_space = mmap(0, ring->mm_len, PROT_READ | PROT_WRITE,
                  MAP_SHARED | MAP_LOCKED | MAP_POPULATE, sock, 0);
    if (ring->mm_space == MAP_FAILED) {
        perror("mmap");
        exit(1);
    }

    memset(ring->rd, 0, ring->rd_len);
    for (i = 0; i < ring->rd_num; ++i) {
        ring->rd[i].iov_base = ring->mm_space + (i * ring->flen);
        ring->rd[i].iov_len = ring->flen;
    }
}

static void bind_ring(int sock, struct ring *ring, const char *iface) {
    int ret;

    ring->ll.sll_family = AF_PACKET;
    ring->ll.sll_protocol = htons(ETH_P_ALL);
    ring->ll.sll_ifindex = if_nametoindex(iface);
    ring->ll.sll_hatype = 0;
    ring->ll.sll_pkttype = 0;
    ring->ll.sll_halen = 0;

    ret = bind(sock, (struct sockaddr *) &ring->ll, sizeof(ring->ll));
    if (ret == -1) {
        perror("bind");
        exit(1);
    }
}

static void unmap_ring(int sock, struct ring *ring) {
    munmap(ring->mm_space, ring->mm_len);
    free(ring->rd);
}

static inline int tx_kernel_ready(struct tpacket3_hdr *hdr) {
    return !(hdr->tp_status & (TP_STATUS_SEND_REQUEST | TP_STATUS_SENDING));
}

static inline void tx_user_ready(struct tpacket3_hdr *hdr) {
    hdr->tp_status = TP_STATUS_SEND_REQUEST;
}
static inline void *get_next_frame(struct ring *ring, int n) {
    uint8_t *f0 = ring->rd[0].iov_base;
    return f0 + (n * ring->req3.tp_frame_size);
}

unsigned int frame_offset = 0;
static void send_pkt(int sock, struct ring *ring, uint8_t * packet, size_t packet_len) {
    int nframes = ring->req3.tp_frame_nr;
    struct tpacket3_hdr *next = get_next_frame(ring, frame_offset);
    while (tx_kernel_ready(next) == 0) {
        frame_offset = (frame_offset + 1) % nframes;
        next = get_next_frame(ring, frame_offset);
    }
    // tx->tp_snaplen = packet_len;
    next->tp_len = packet_len;
    next->tp_next_offset = 0;
    memcpy((uint8_t *)next + TPACKET3_HDRLEN - sizeof(struct sockaddr_ll), packet,
    packet_len);
    next->tp_status = TP_STATUS_SEND_REQUEST;
    frame_offset = (frame_offset + 1) % nframes;
    int ret = sendto(sock, NULL, 0, 0, NULL, 0);
    if (ret == -1) {
        perror("sendto");
        exit(1);
    }
}

void *ctrl_set_bw(void *data, struct nl_sock *qdisc_sock, struct rtnl_qdisc *fq_qdisc) {
    ctrl_pckt *pkt = (ctrl_pckt *) data;
    uint64_t tx_rate = atol(pkt->buf_size);
    // int test = rtnl_qdisc_tbf_get_rate (fq_qdisc);
    // fprintf(stderr,"tx_rate: %.3fmbit old %.3fmbit\n", tx_rate / 10e5, test / 10e5);
    // snprintf(cmd, 200, "tc class change dev %s parent 5:0 classid 5:1 htb rate %lu burst 15k", iface, tx_rate);
    // char cmd[200];
    // snprintf(cmd, 200,"tc qdisc change dev %s root fq maxrate %.3fmbit", iface, tx_rate / 10e5);
    // fprintf(stderr, "Host %s: cmd: %s\n", iface, cmd);
    rtnl_qdisc_tbf_set_limit(fq_qdisc, tx_rate);
    rtnl_qdisc_tbf_set_rate(fq_qdisc, tx_rate/8, 15000, 0);
    rtnl_qdisc_add(qdisc_sock, fq_qdisc, NLM_F_REPLACE);

    return NULL;
}

void ctrl_handle(struct tpacket3_hdr *ppd, struct nl_sock *qdisc_sock, struct rtnl_qdisc *fq_qdisc) {
    // Interpret rx packet headers
    struct ethhdr *eth_hdr_rx = (struct ethhdr *)((uint8_t *) ppd + ppd->tp_mac);
    struct iphdr *ip_hdr_rx = (struct iphdr *)((uint8_t *)eth_hdr_rx + ETH_HLEN);
    struct udphdr *udp_hdr_rx = (struct udphdr *)((uint8_t *)eth_hdr_rx + ETH_HLEN + sizeof(*ip_hdr_rx));
    uint8_t *data_rx = ((uint8_t *)eth_hdr_rx + ETH_HLEN + sizeof(*ip_hdr_rx) + sizeof(*udp_hdr_rx));

    // set the bandwidth of the interface
    ctrl_set_bw(data_rx, qdisc_sock, fq_qdisc);

    // create a new packet with the same length and copy it from the rx ring
    uint16_t pkt_len = ppd->tp_snaplen
;    uint8_t packet[pkt_len];
    memcpy(packet, eth_hdr_rx, pkt_len);
    printf("%d\n", pkt_len );
    // Interpret cloned packet headers
    struct ethhdr *eth_hdr_tx = (struct ethhdr *)((uint8_t *) packet);
    struct iphdr *ip_hdr_tx = (struct iphdr *)((uint8_t *)eth_hdr_tx + ETH_HLEN);
    struct udphdr *udp_hdr_tx = (struct udphdr *)((uint8_t *)eth_hdr_tx + ETH_HLEN + sizeof(*ip_hdr_tx));

    // flip src and dst mac, ip, und udp ports
    memcpy(eth_hdr_tx->h_dest, eth_hdr_rx->h_source, 6);
    memcpy(eth_hdr_tx->h_source, eth_hdr_rx->h_dest, 6);
    ip_hdr_tx->saddr = ip_hdr_rx->daddr;
    ip_hdr_tx->daddr = ip_hdr_rx->saddr;
    udp_hdr_tx->source = udp_hdr_rx->dest;
    udp_hdr_tx->dest = udp_hdr_rx->source;
    // bounce the packet back
    send_pkt(sock_tx, &ring_tx, packet, pkt_len);
}

static void walk_block(struct block_desc *pbd, const int block_num, struct nl_sock *qdisc_sock, struct rtnl_qdisc *fq_qdisc) {
    int num_pkts = pbd->h1.num_pkts, i;
    struct tpacket3_hdr *ppd;

    ppd = (struct tpacket3_hdr *) ((uint8_t *) pbd +
                       pbd->h1.offset_to_first_pkt);
    for (i = 0; i < num_pkts; ++i) {
        ctrl_handle(ppd, qdisc_sock, fq_qdisc);
        ppd = (struct tpacket3_hdr *) ((uint8_t *) ppd +
                           ppd->tp_next_offset);
    }
}

static void flush_block(struct block_desc *pbd) {
    pbd->h1.block_status = TP_STATUS_KERNEL;
}

static sig_atomic_t sigint = 0;

static void sighandler(int num) {
    sigint = 1;
}

void usage(char *prog_name){
    printf("usage: %s [args]\n", prog_name);
    printf("-n <netdev> - the interface attached to the main network\n");
    printf("-c <ctrldev>- the interface attached to the control network\n");
    exit(1);
}

int main(int argc, char **argv) {
    int ret = 0, err = 0;

    // process args
    char c;
    char *netdev = NULL;
    char *ctrldev = NULL;
    char *prog_name = argv[0];
    opterr = 0;
    while ((c = getopt(argc, argv, "n:c:")) != -1)
    {
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


    /* init qdisc on the device */
    char tc_cmd[200];
    snprintf(tc_cmd, 200, "tc qdisc del dev %s root", netdev);
    err = system(tc_cmd);
    if (err)
        perror("Problem with tc del");
    // snprintf(tc_cmd, 200,"tc qdisc add dev %s root fq maxrate %.3fmbit", netdev, 10e6 / 10e5);
    // err = system(tc_cmd);
    // if (err)
    //     perror("Problem with tc add");

    struct nl_sock *qdisc_sock;
    struct rtnl_qdisc *fq_qdisc;
    struct nl_cache *cache;
    struct rtnl_link *link;
    int if_index;

    qdisc_sock = nl_socket_alloc();
    nl_connect(qdisc_sock, NETLINK_ROUTE);
    rtnl_link_alloc_cache(qdisc_sock, AF_UNSPEC, &cache);
    link = rtnl_link_get_by_name(cache, netdev);
    if_index = rtnl_link_get_ifindex(link);
    fq_qdisc = rtnl_qdisc_alloc();
    rtnl_tc_set_ifindex(TC_CAST(fq_qdisc), if_index);
    rtnl_tc_set_parent(TC_CAST(fq_qdisc), TC_H_ROOT);
    rtnl_tc_set_handle(TC_CAST(fq_qdisc), TC_HANDLE(1, 0));
    rtnl_tc_set_kind(TC_CAST(fq_qdisc), "tbf");
    rtnl_qdisc_tbf_set_limit(fq_qdisc, 10e6);
    rtnl_qdisc_tbf_set_rate(fq_qdisc, 10e6/8, 15000, 0);

    rtnl_qdisc_add(qdisc_sock, fq_qdisc, NLM_F_CREATE);


    struct pollfd pfd;
    struct block_desc *pbd;
    unsigned int block_num = 0;
    sock_rx = init_socket(TPACKET_V3, netdev, CTRL_PORT);
    sock_tx = init_socket(TPACKET_V3, netdev, CTRL_PORT);
    memset(&ring_rx, 0, sizeof(ring_rx));
    memset(&ring_tx, 0, sizeof(ring_tx));
    setup_ring(sock_rx, &ring_rx, TPACKET_V3, PACKET_RX_RING);
    setup_ring(sock_tx, &ring_tx, TPACKET_V3, PACKET_TX_RING);

    mmap_ring(sock_rx, &ring_rx);
    mmap_ring(sock_tx, &ring_tx);

    bind_ring(sock_rx, &ring_rx, ctrldev);
    bind_ring(sock_tx, &ring_tx, ctrldev);

    memset(&pfd, 0, sizeof(pfd));
    pfd.fd = sock_rx;
    pfd.events = POLLIN | POLLERR;
    pfd.revents = 0;

    while (likely(!sigint)) {
        pbd = (struct block_desc *) ring_rx.rd[block_num].iov_base;

        if ((pbd->h1.block_status & TP_STATUS_USER) == 0) {
            poll(&pfd, 1, -1);
            continue;
        }

        walk_block(pbd, block_num, qdisc_sock, fq_qdisc);
        flush_block(pbd);
        block_num = (block_num + 1) % 256;
    }

    rtnl_qdisc_put(fq_qdisc);
    nl_socket_free(qdisc_sock);
    rtnl_link_put(link);
    nl_cache_put(cache);

    unmap_ring(sock_rx, &ring_rx);
    unmap_ring(sock_tx, &ring_tx);

    close(sock_rx);
    close(sock_tx);

    if (ret)
        return 1;

    return 0;
}
