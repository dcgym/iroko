#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <net/if.h>
#include <arpa/inet.h>
#include <netdb.h>
#include <poll.h>
#include <unistd.h>
#include <signal.h>
#include <inttypes.h>
#include <sys/socket.h>
#include <sys/mman.h>
#include <linux/if_packet.h>
#include <linux/if_ether.h>

#include <netinet/udp.h>   //Provides declarations for udp header
#include <netinet/tcp.h>   //Provides declarations for tcp header
#include <netinet/ip.h> //Provides declarations for ip header
#include <sys/poll.h>         // pollfd, poll
#include <linux/filter.h>     // struct sock_fprog
#include<limits.h>

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

#define CNTRL_PORT  20130
#define CNTRL_PCKT_SIZE 9450
typedef struct cntrl_pckt {
    char buf_size[20];
} cntrl_pckt;

struct block_desc {
    uint32_t version;
    uint32_t offset_to_priv;
    struct tpacket_hdr_v1 h1;
};

struct ring {
    struct iovec *rd;
    uint8_t *map;
    struct tpacket_req3 req;
};

static unsigned long packets_total = 0, bytes_total = 0;
static sig_atomic_t sigint = 0;

static void sighandler(int num) {
    sigint = 1;
}

int cntrl_fd;
struct ring ring;

// Super shitty hack. Do not try this at home kids.
int set_packet_filter(int sd, const char *iface, int port) {
    struct sock_fprog filter;
    int i, lineCount = 0;
    char cmd[512];
    FILE* tcpdump_output;
    sprintf(cmd, "tcpdump -i %s dst port %d and udp -ddd", iface, port);

    printf("Active Filter: %s\n",cmd );
    if ( (tcpdump_output = popen(cmd, "r")) == NULL )
        RETURN_ERROR(-1, "Cannot compile filter using tcpdump.");
    if (fscanf(tcpdump_output, "%d\n", &lineCount) < 1 )
        RETURN_ERROR(-1, "cannot read lineCount.");
    filter.filter = (struct sock_filter *)calloc(1, sizeof(struct sock_filter)*lineCount);
    filter.len = lineCount;
    for (i = 0; i < lineCount; i++) {
        if (fscanf(tcpdump_output, "%u %u %u %u\n", (unsigned int *)&(filter.filter[i].code),(unsigned int *) &(filter.filter[i].jt),(unsigned int *) &(filter.filter[i].jf), &(filter.filter[i].k)) < 4 ) {
            free(filter.filter);
            RETURN_ERROR(-1, "fscanf: error in reading");
        }
        setsockopt(sd, SOL_SOCKET, SO_ATTACH_FILTER, &filter, sizeof(filter));
    }
    pclose(tcpdump_output);
    free(filter.filter);
    return EXIT_SUCCESS;
}


static int setup_socket(struct ring *ring, const char *netdev, int port) {
    int err, fd, v = TPACKET_V3;
    struct sockaddr_ll ll;
    unsigned int blocksiz = 1 << 22, framesiz = 1 << 11;
    unsigned int blocknum = 64;

    fd = socket(AF_PACKET, SOCK_RAW, htons(ETH_P_ALL));
    if (fd < 0) {
        perror("socket");
        exit(1);
    }
    set_packet_filter(fd, netdev, port);
    err = setsockopt(fd, SOL_PACKET, PACKET_VERSION, &v, sizeof(v));
    if (err < 0) {
        perror("setsockopt");
        exit(1);
    }
    memset(&ring->req, 0, sizeof(ring->req));
    ring->req.tp_block_size = blocksiz;
    ring->req.tp_frame_size = framesiz;
    ring->req.tp_block_nr = blocknum;
    ring->req.tp_frame_nr = (blocksiz * blocknum) / framesiz;
    ring->req.tp_retire_blk_tov = 60;
    ring->req.tp_feature_req_word = TP_FT_REQ_FILL_RXHASH;


    err = setsockopt(fd, SOL_PACKET, PACKET_RX_RING, &ring->req,
             sizeof(ring->req));
    if (err < 0) {
        perror("setsockopt");
        exit(1);
    }

    ring->map = (uint8_t*) mmap(NULL, ring->req.tp_block_size * ring->req.tp_block_nr, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_LOCKED, fd, 0);
    if (ring->map == MAP_FAILED) {
        perror("mmap");
        exit(1);
    }

    ring->rd = (struct iovec*) malloc(ring->req.tp_block_nr * sizeof(*ring->rd));
    assert(ring->rd);
    for (uint64_t i = 0; i < ring->req.tp_block_nr; ++i) {
        ring->rd[i].iov_base = ring->map + (i * ring->req.tp_block_size);
        ring->rd[i].iov_len = ring->req.tp_block_size;
    }

    memset(&ll, 0, sizeof(ll));
    ll.sll_family = PF_PACKET;
    ll.sll_protocol = htons(ETH_P_ALL);
    ll.sll_ifindex = if_nametoindex(netdev);
    ll.sll_hatype = 0;
    ll.sll_pkttype = 0;
    ll.sll_halen = 0;

    err = bind(fd, (struct sockaddr *) &ll, sizeof(ll));
    if (err < 0) {
        perror("bind");
        exit(1);
    }

    return fd;
}


char cmd[200];
void *cntrl_thread_main(struct tpacket3_hdr *ppd, const char *iface) {
    struct eth_hdr *eth_hdr = (struct eth_hdr *)((uint8_t *) ppd + ppd->tp_mac);
    struct iphdr *ip_hdr = (struct iphdr *)((uint8_t *)eth_hdr + ETH_HLEN);
    struct udphdr *udp_hdr = (struct udphdr *)((uint8_t *)eth_hdr + ETH_HLEN + sizeof(*ip_hdr));
    uint8_t *data = ((uint8_t *)eth_hdr + ETH_HLEN + sizeof(*ip_hdr) + sizeof(*udp_hdr));
    cntrl_pckt *pkt = (cntrl_pckt *) data;
    uint64_t tx_rate = atol(pkt->buf_size);
    // fprintf(stderr,"Host %s: tx_rate: %.3fmbit\n", iface, tx_rate / 10e5);
    // snprintf(cmd, 200, "tc class change dev %s parent 5:0 classid 5:1 htb rate %lu burst 15k", iface, tx_rate);

    snprintf(cmd, 200,"tc qdisc change dev %s root fq maxrate %.3fmbit", iface, tx_rate / 10e5);
    // fprintf(stderr, "Host %s: cmd: %s\n", iface, cmd);
    int ret = system(cmd);
    if (ret)
        perror("Problem with tc");

    return NULL;
}

static void walk_block(struct block_desc *pbd, const int block_num, const char *iface) {
    int num_pkts = pbd->h1.num_pkts, i;
    unsigned long bytes = 0;
    struct tpacket3_hdr *ppd;

    ppd = (struct tpacket3_hdr *) ((uint8_t *) pbd +
                       pbd->h1.offset_to_first_pkt);
    for (i = 0; i < num_pkts; ++i) {
        bytes += ppd->tp_snaplen;
        cntrl_thread_main(ppd, iface);
        ppd = (struct tpacket3_hdr *) ((uint8_t *) ppd +
                           ppd->tp_next_offset);
    }

    packets_total += num_pkts;
    bytes_total += bytes;
}

static void flush_block(struct block_desc *pbd) {
    pbd->h1.block_status = TP_STATUS_KERNEL;
}

static void teardown_socket(struct ring *ring, int fd) {
    munmap(ring->map, ring->req.tp_block_size * ring->req.tp_block_nr);
    free(ring->rd);
    close(fd);
}

void usage(char *prog_name){
    printf("usage: %s [args]\n", prog_name);
    printf("-n <net_dev> - the interface attached to the main network\n");
    printf("-c <ctrl_dev>- the interface attached to the control network\n");
    exit(1);
}

int main(int argc, char **argv) {
    int fd, err;
    socklen_t len;
    struct ring ring;
    struct pollfd pfd;
    unsigned int block_num = 0, blocks = 64;
    struct block_desc *pbd;
    struct tpacket_stats_v3 stats;
    // process args
    char c;
    char *net_dev = NULL;
    char *ctrl_dev = NULL;
    char *prog_name = argv[0];
    opterr = 0;
    while ((c = getopt(argc, argv, "n:c:")) != -1)
    {
        switch(c)
        {
            case 'n':
                net_dev = optarg;
                break;
            case 'c':
                ctrl_dev = optarg;
                break;
            case '?':
                printf("unknown option: %c\n", optopt);
                usage(prog_name);
        }
    }
    if (!(net_dev && ctrl_dev))
        usage(prog_name);
    signal(SIGINT, sighandler);

    memset(&ring, 0, sizeof(ring));
    fd = setup_socket(&ring, ctrl_dev, CNTRL_PORT);
    assert(fd > 0);

    memset(&pfd, 0, sizeof(pfd));
    pfd.fd = fd;
    pfd.events = POLLIN | POLLERR;
    pfd.revents = 0;

    /* init qdisc on the device */
    char tc_cmd[200];
    snprintf(tc_cmd, 200, "tc qdisc del dev %s root", net_dev);
    err = system(tc_cmd);
    if (err)
        perror("Problem with tc del");
    snprintf(tc_cmd, 200,"tc qdisc add dev %s root fq maxrate %.3fmbit", net_dev, 10e6 / 10e5);
    err = system(tc_cmd);
    if (err)
        perror("Problem with tc add");
    while (likely(!sigint)) {
        pbd = (struct block_desc *) ring.rd[block_num].iov_base;

        if ((pbd->h1.block_status & TP_STATUS_USER) == 0) {
            poll(&pfd, 1, -1);
            continue;
        }

        walk_block(pbd, block_num, net_dev);
        flush_block(pbd);
        block_num = (block_num + 1) % blocks;
    }

    len = sizeof(stats);
    err = getsockopt(fd, SOL_PACKET, PACKET_STATISTICS, &stats, &len);
    if (err < 0) {
        perror("getsockopt");
        exit(1);
    }

    fflush(stdout);
    teardown_socket(&ring, fd);
    return 0;
}