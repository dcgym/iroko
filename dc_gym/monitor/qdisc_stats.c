#include <net/if.h> // if_nametoindex
#include <libnl3/netlink/route/qdisc.h>
#include <netlink/object-api.h> // nl_object_free()


struct rtnl_qdisc *init_qdisc_monitor(char *interface) {
    struct nl_sock *sock;
    struct nl_cache *qdisc_cache;
    struct rtnl_qdisc *qdisc;
    int ifindex, err;
    ifindex = if_nametoindex(interface);
    /* Allocate a netlink socket and connect it with the netlink route module */
    sock = nl_socket_alloc();
    if(!sock)
        fprintf(stderr,"Could not allocated socket!\n");
    err = nl_connect(sock, NETLINK_ROUTE);
    if (err)
        fprintf(stderr,"nl_connect: %s\n", nl_geterror(err));
    /* Get all active qdiscs and find the main qdisc of the target interface*/
    err =rtnl_qdisc_alloc_cache(sock, &qdisc_cache);
    if (err)
        fprintf(stderr,"qdisc_alloc_cache: %s\n", nl_geterror(err));
    qdisc = rtnl_qdisc_get_by_parent(qdisc_cache, ifindex, TC_H_ROOT);
    if(!qdisc) {
        fprintf(stderr,"Qdisc for interface %s not found!\n", interface);
        return NULL;
    }
    /* Free all allocated data structures */
    nl_cache_free(qdisc_cache);
    nl_socket_free(sock);
    return qdisc;
}

int get_qdisc_packets(struct rtnl_qdisc *qdisc) {
    /* Query current queue length on the interface */
    int get_qdisc_backlog = rtnl_tc_get_stat(TC_CAST(qdisc), RTNL_TC_PACKETS);
    return get_qdisc_backlog;
}

int get_qdisc_bytes(struct rtnl_qdisc *qdisc) {
    /* Query current queue length on the interface */
    int get_qdisc_backlog = rtnl_tc_get_stat(TC_CAST(qdisc), RTNL_TC_BYTES);
    return get_qdisc_backlog;
}

int get_qdisc_rate_bps(struct rtnl_qdisc *qdisc) {
    /* Query current queue length on the interface */
    int get_qdisc_backlog = rtnl_tc_get_stat(TC_CAST(qdisc), RTNL_TC_RATE_BPS);
    return get_qdisc_backlog;
}

int get_qdisc_rate_pps(struct rtnl_qdisc *qdisc) {
    /* Query current queue length on the interface */
    int get_qdisc_backlog = rtnl_tc_get_stat(TC_CAST(qdisc), RTNL_TC_RATE_PPS);
    return get_qdisc_backlog;
}

int get_qdisc_qlen(struct rtnl_qdisc *qdisc) {
    /* Query current queue length on the interface */
    int get_qdisc_backlog = rtnl_tc_get_stat(TC_CAST(qdisc), RTNL_TC_QLEN);
    return get_qdisc_backlog;
}

int get_qdisc_backlog(struct rtnl_qdisc *qdisc) {
    /* Query current queue length on the interface */
    int get_qdisc_backlog = rtnl_tc_get_stat(TC_CAST(qdisc), RTNL_TC_BACKLOG);
    return get_qdisc_backlog;
}

int get_qdisc_drops(struct rtnl_qdisc *qdisc) {
    /* Query current queue length on the interface */
    int get_qdisc_backlog = rtnl_tc_get_stat(TC_CAST(qdisc), RTNL_TC_DROPS);
    return get_qdisc_backlog;
}

int get_qdisc_requeues(struct rtnl_qdisc *qdisc) {
    /* Query current queue length on the interface */
    int get_qdisc_backlog = rtnl_tc_get_stat(TC_CAST(qdisc), RTNL_TC_REQUEUES);
    return get_qdisc_backlog;
}

int get_qdisc_overlimits(struct rtnl_qdisc *qdisc) {
    /* Query current queue length on the interface */
    int get_qdisc_backlog = rtnl_tc_get_stat(TC_CAST(qdisc), RTNL_TC_OVERLIMITS);
    return get_qdisc_backlog;
}

void delete_qdisc_monitor(struct rtnl_qdisc *qdisc) {
    nl_object_free((struct nl_object *) qdisc);

}
// Minimal test to verify functionality
// int main(int argc, char ** argv) {
//     int num_ifaces = 1;
//     char *ifaces[] = {"enp0s31f6"};

//     for (int i = 0; i < num_ifaces; i++) {
//         int queue_len = get_iface_queue(ifaces[i]);
//         printf("%d ", queue_len);
//     }
//     printf("\n");
//     return 0;
// }