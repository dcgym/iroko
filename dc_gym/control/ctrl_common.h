#ifndef CTRL_COMMON_H
#define CTRL_COMMON_H

#include "raw_udp_socket.h"
#include <stdio.h>
#include <string.h>
#include <stdio.h>

typedef struct ctrl_pckt {
    uint64_t tx_rate;
} ctrl_pckt;


#ifdef QDISC_FQ
#define HANDLE_TYPE char
#elif QDISC_TBF
struct rtnl_qdisc;
#define HANDLE_TYPE struct rtnl_qdisc
#elif QDISC_HTB
struct rtnl_qdisc;
#define HANDLE_TYPE struct rtnl_qdisc
#else
#define HANDLE_TYPE void
#endif

int ctrl_set_bw(void *data, HANDLE_TYPE *ctrl_handle);
HANDLE_TYPE *setup_qdisc(char *netdev, long rate);
int clean_qdisc(HANDLE_TYPE *ctrl_handle);

#endif // CTRL_COMMON_H