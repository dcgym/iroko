#ifndef RAW_UDP_SOCKET_H
#define RAW_UDP_SOCKET_H
#include <linux/if_packet.h>    // packet_mmap
#include <net/ethernet.h>       // Ethernet header declarations
#include <netinet/ip.h>         // IP header declarations
#include <netinet/udp.h>        // UDP header declarations
#include <linux/version.h>      // Linux version check
#include <poll.h>               // polling descriptors
#include <stdlib.h>

// Older kernel versions do not support TPACKET_V3.
// Something is wrong with TPACKET_V3, so let's always use TPACKET_V2 for now.
#if LINUX_VERSION_CODE <= KERNEL_VERSION(4,15,0)
#endif
#define PACKET_MMAPV2

// (unimportant) macro for loud failure
// needs some love in the code
#define RETURN_ERROR(lvl, msg) \
  do {                    \
    perror(msg); \
    return lvl;            \
  } while(0);

#ifndef likely
# define likely(x)      __builtin_expect(!!(x), 1)
#endif
#ifndef unlikely
# define unlikely(x)        __builtin_expect(!!(x), 0)
#endif

#define IP_HDRLEN sizeof(struct iphdr)   // IP header length
#define UDP_HDRLEN sizeof(struct udphdr)   // UDP header length, excludes data
#define HDRS_LEN ETH_HLEN + IP_HDRLEN + UDP_HDRLEN

struct ring {
    struct iovec *rd;
    uint8_t *mm_space;
    size_t mm_len, rd_len;
    struct sockaddr_ll ll;
    void (*walk)(int sock, struct ring *ring);
    int type, rd_num, flen;
    int socket;             // socket associated with ring
    struct pollfd pfd;      // poll descriptor for associated socket
    int p_offset;           // current offset in the ring
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

struct ring *init_raw_backend(const char *iface, int port, int type);
void teardown_raw_backend(struct ring *ring);
int send_pkt(struct ring *ring, uint8_t *packet, size_t packet_len);

#endif // RAW_UDP_SOCKET_H