#include <net/if.h>
#include <libnl3/netlink/route/qdisc.h>
#include <libnl3/netlink/route/qdisc/netem.h>

int get_iface_queue(char *interface) {
    struct nl_sock *sock;
    struct nl_cache *nl_cache;
    struct nl_cache *qdisc_cache;
    struct rtnl_qdisc *qdisc;
    sock = nl_socket_alloc();
    nl_connect(sock, NETLINK_ROUTE);
    rtnl_link_alloc_cache(sock, AF_UNSPEC, &nl_cache);
    rtnl_qdisc_alloc_cache(sock, &qdisc_cache);
    int ifindex = if_nametoindex(interface);
    qdisc = rtnl_qdisc_get_by_parent(qdisc_cache, ifindex, TC_H_ROOT);
    int qdisc_len = rtnl_tc_get_stat(TC_CAST(qdisc),  RTNL_TC_QLEN);
    nl_socket_free(sock);
    nl_cache_put(nl_cache);
    return qdisc_len;
}

// int main(int argc, char ** argv) {
//     int num_ifaces = 6;
//     char *ifaces[] = {"sw1-eth1", "sw1-eth2", "sw1-eth3", "sw2-eth1", "sw2-eth2","sw2-eth3"};
//     for (int i = 0; i < num_ifaces; i++) {
//         int queue_len = get_iface_queue(ifaces[i]);
//         printf("%d ", queue_len);
//     }
//     printf("\n");
//     return 0;
// }