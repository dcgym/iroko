#include "ctrl_common.h"

#define HANDLE_TYPE char

int ctrl_set_bw(void *data, HANDLE_TYPE *ctrl_handle) {
    char tc_cmd[200];
    int err = 0;
    float tx_rate;
    ctrl_pckt *pkt;
    pkt = (ctrl_pckt *) data;
    tx_rate = pkt->tx_rate;
    // fprintf(stderr,"Host %s: tx_rate: %.3fmbit\n", iface, tx_rate / 10e5);
    snprintf(tc_cmd, 200,"tc qdisc change dev %s root fq maxrate %.3fmbit &", ctrl_handle, tx_rate / 10e5);
    // fprintf(stderr, "Host %s: tc_cmd: %s\n", iface, tc_cmd);
    err = system(tc_cmd);
    if (err)
        RETURN_ERROR(EXIT_FAILURE, "Problem with tc qdisc change");
    return EXIT_SUCCESS;
}

HANDLE_TYPE *setup_qdisc(char *netdev, long rate){
    int err = 0;
    char tc_cmd[200];
    snprintf(tc_cmd, 200,"tc qdisc add dev %s root fq maxrate %lubit", netdev, rate);
    err = system(tc_cmd);
    if (err)
        RETURN_ERROR(NULL, "Problem with tc add");
    return netdev;
}


int clean_qdisc(HANDLE_TYPE *ctrl_handle){
    return EXIT_SUCCESS;
}