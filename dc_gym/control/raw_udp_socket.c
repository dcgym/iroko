#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <linux/filter.h>
#include <unistd.h>
#include <string.h>
#include <net/if.h>

#include "raw_udp_socket.h"


// Super shitty hack. Do not try this at home kids.
int set_packet_filter(int sd, const char *iface, int port) {
    struct sock_fprog filter;
    int i, lineCount = 0;
    char cmd[512];
    FILE* tcpdump_output;
    sprintf(cmd, "tcpdump -i %s dst port %d and udp -ddd", iface, port);
    // printf("Active Filter: %s\n",cmd );
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

static int init_socket(int ver, const char *netdev) {
    int ret, sock = socket(AF_PACKET, SOCK_RAW, 0);
    if (sock == -1) {
        perror("socket");
        exit(1);
    }

    ret = setsockopt(sock, SOL_PACKET, PACKET_VERSION, &ver, sizeof(ver));
    if (ret == -1) {
        perror("setsockopt");
        exit(1);
    }
    return sock;
}

static void __v2_fill(struct ring *ring, unsigned int blocks) {
    ring->req.tp_block_size = getpagesize() << 2;
    ring->req.tp_frame_size = TPACKET_ALIGNMENT << 7;
    ring->req.tp_block_nr = blocks;

    ring->req.tp_frame_nr = ring->req.tp_block_size /
                ring->req.tp_frame_size *
                ring->req.tp_block_nr;

    ring->mm_len = ring->req.tp_block_size * ring->req.tp_block_nr;
    ring->rd_num = ring->req.tp_frame_nr;
    ring->flen = ring->req.tp_frame_size;
}

static void __v3_fill(struct ring *ring, unsigned int blocks, int type) {
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

    switch (version) {
    case TPACKET_V2:
        __v2_fill(ring, blocks);
        ret = setsockopt(sock, SOL_PACKET, type, &ring->req,
                 sizeof(ring->req));
        break;

    case TPACKET_V3:
        __v3_fill(ring, blocks, type);
        ret = setsockopt(sock, SOL_PACKET, type, &ring->req3,
                 sizeof(ring->req3));
        break;
    }

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

    ring->mm_space = mmap(0, ring->mm_len, PROT_READ | PROT_WRITE,
                  MAP_SHARED | MAP_LOCKED | MAP_POPULATE, sock, 0);
    if (ring->mm_space == MAP_FAILED) {
        perror("mmap");
        exit(1);
    }

    memset(ring->rd, 0, ring->rd_len);
    for (int i = 0; i < ring->rd_num; ++i) {
        ring->rd[i].iov_base = ring->mm_space + (i * ring->flen);
        ring->rd[i].iov_len = ring->flen;
    }
}

static void bind_ring(int sock, struct ring *ring, const char *iface, int port) {
    int ret;

    ring->ll.sll_family = AF_PACKET;
    ring->ll.sll_protocol = htons(ETH_P_ALL);
    ring->ll.sll_ifindex = if_nametoindex(iface);
    ring->ll.sll_hatype = 0;
    ring->ll.sll_pkttype = 0;
    ring->ll.sll_halen = 0;

    // if (ring->type == PACKET_RX_RING) {
    //     int ret = set_packet_filter(ring->socket, iface, port);
    //     if (ret == -1) {
    //         perror("filter");
    //         exit(1);
    //     }
    // }

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

static inline int tx_kernel_ready(void *base) {
#ifdef PACKET_MMAPV2
    struct tpacket2_hdr *hdr = (struct tpacket2_hdr *) base;
#else
    struct tpacket3_hdr *hdr = (struct tpacket3_hdr *) base;
#endif
    return !(hdr->tp_status & (TP_STATUS_SEND_REQUEST | TP_STATUS_SENDING));
}

static inline void *get_next_frame(struct ring *ring, int n) {
#ifdef PACKET_MMAPV2
    return ring->rd[n].iov_base;
#else
    uint8_t *f0 = ring->rd[0].iov_base;
    return f0 + (n * ring->req3.tp_frame_size);
#endif
}

struct ring *init_raw_backend(const char *iface, int port, int type) {
#ifdef PACKET_MMAPV2
    // fprintf(stderr, "Using tpacket_v2.\n");
    int version = TPACKET_V2;
#else
    int version = TPACKET_V3;
#endif
    struct ring *ring = malloc(sizeof(struct ring));
    memset(ring, 0, sizeof(struct ring));
    ring->socket = init_socket(version, iface);
    if (type == PACKET_RX_RING) {
        int ret = set_packet_filter(ring->socket, iface, port);
        if (ret == -1) {
            perror("filter");
            exit(1);
        }
    }
    setup_ring(ring->socket, ring, version, type);
    mmap_ring(ring->socket, ring);
    bind_ring(ring->socket, ring, iface, port);
    return ring;
}

void teardown_raw_backend(struct ring *ring) {
    unmap_ring(ring->socket, ring);
    close(ring->socket);
    free(ring);
}

int send_pkt(struct ring *ring, uint8_t *packet, size_t packet_len) {
#ifdef PACKET_MMAPV2
    int nframes = ring->rd_num;
    struct tpacket2_hdr *next = get_next_frame(ring, ring->p_offset);
#else
    struct tpacket3_hdr *next = get_next_frame(ring, ring->p_offset);
    int nframes = ring->req3.tp_frame_nr;
#endif
    while (tx_kernel_ready(next) == 0) {
        ring->p_offset = (ring->p_offset + 1) % nframes;
        next = get_next_frame(ring, ring->p_offset);
    }
    // tx->tp_snaplen = packet_len;
    next->tp_len = packet_len;
#ifdef PACKET_MMAPV2
    memcpy((uint8_t *)next + TPACKET2_HDRLEN - sizeof(struct sockaddr_ll), packet, packet_len);
#else
    next->tp_next_offset = 0;
    memcpy((uint8_t *)next + TPACKET3_HDRLEN - sizeof(struct sockaddr_ll), packet, packet_len);
#endif

    next->tp_status = TP_STATUS_SEND_REQUEST;
    ring->p_offset = (ring->p_offset + 1) % nframes;
    int ret = sendto(ring->socket, NULL, 0, 0, NULL, 0);
    if (ret == -1)
        RETURN_ERROR(EXIT_FAILURE, "sendto:");
    return EXIT_SUCCESS;
}
