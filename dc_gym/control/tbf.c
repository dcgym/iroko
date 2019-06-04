#include <libnl3/netlink/route/tc.h>
#include <libnl3/netlink/route/qdisc.h>
#include <libnl3/netlink/route/qdisc/netem.h>
#include <libnl3/netlink/route/qdisc/tbf.h>
#include <libnl3/netlink/route/qdisc/htb.h>
#include <net/if.h>

#include "ctrl_common.h"

static struct nl_sock *qdisc_sock;

int ctrl_set_bw(void *data, HANDLE_TYPE *ctrl_handle) {
    int err = 0;
    float tx_rate;
    ctrl_pckt *pkt;
    uint32_t burst;
    uint32_t limit;

    limit = 1530;
    burst = 5000;
    pkt = (ctrl_pckt *) data;
    tx_rate = pkt->tx_rate / 8.0;
    // used for debugging purposes
    // int old_rate = rtnl_qdisc_tbf_get_rate (fq_qdisc);
    // fprintf(stderr,"tx_rate: %.3fmbit old %.3fmbit\n", tx_rate* 8 / 1e6,
    //         old_rate*8 / 1e6);
    // fprintf(stderr, "Burst %lu Limit %lu\n", burst, limit);
    rtnl_qdisc_tbf_set_rate(ctrl_handle, (uint32_t) tx_rate, burst , 0);
    rtnl_qdisc_tbf_set_peakrate(ctrl_handle, (uint32_t) tx_rate, burst, 0);
    // rtnl_qdisc_tbf_set_limit(ctrl_handle, limit);
    rtnl_qdisc_tbf_set_limit_by_latency(ctrl_handle, 0);
    err = rtnl_qdisc_add(qdisc_sock, ctrl_handle, NLM_F_REPLACE);
    if(err) {
        fprintf(stderr,"Rate %lu qdisc_add: %s\n", pkt->tx_rate, nl_geterror(err));
        return EXIT_FAILURE;
    }
    return EXIT_SUCCESS;
}

HANDLE_TYPE  *setup_qdisc(char *netdev, long rate){
    struct rtnl_qdisc *fq_qdisc;
    int if_index;
    int err = 0;
    uint32_t burst = 12000;
    uint32_t limit = 1550;

    fprintf(stderr, "Kernel Clock Rate: %d\n", nl_get_user_hz());
    qdisc_sock = nl_socket_alloc();
    nl_connect(qdisc_sock, NETLINK_ROUTE);
    if_index = if_nametoindex(netdev);
    fq_qdisc = rtnl_qdisc_alloc();
    rtnl_tc_set_ifindex(TC_CAST(fq_qdisc), if_index);
    rtnl_tc_set_parent(TC_CAST(fq_qdisc), TC_H_ROOT);
    rtnl_tc_set_handle(TC_CAST(fq_qdisc), TC_HANDLE(1,0));
    rtnl_tc_set_mpu(TC_CAST(fq_qdisc), 0);
    rtnl_tc_set_mtu(TC_CAST(fq_qdisc), 1500);

    err = rtnl_tc_set_kind(TC_CAST(fq_qdisc), "tbf");
    if (err) {
        fprintf(stderr,"Can not allocate TBF: %s\n", nl_geterror(err));
        return NULL;
    }
    // fprintf(stderr, "Calculated limit: %lu \n", limit);
    rtnl_qdisc_tbf_set_rate(fq_qdisc, (uint32_t) rate, burst , 0);
    rtnl_qdisc_tbf_set_limit(fq_qdisc, limit);
    rtnl_qdisc_tbf_set_peakrate(fq_qdisc, (uint32_t) rate, burst, 0);
    err = rtnl_qdisc_add(qdisc_sock, fq_qdisc, NLM_F_CREATE);
    if (err) {
        fprintf(stderr,"Can not set TBF: %s\n", nl_geterror(err));
        return NULL;
    }
    return fq_qdisc;
}

int clean_qdisc(HANDLE_TYPE  *ctrl_handle) {
    nl_socket_free(qdisc_sock);
    nl_object_free((struct nl_object *) ctrl_handle);
    return EXIT_SUCCESS;
}
