struct rtnl_class *setup_class(struct nl_sock *qdisc_sock, const char *netdev, long rate){
    struct rtnl_class *fq_class;
    int if_index;
    int err = 0;

    if_index = if_nametoindex(netdev);
    fq_class = rtnl_class_alloc();
    rtnl_tc_set_ifindex(TC_CAST(fq_class), if_index);
    rtnl_tc_set_parent(TC_CAST(fq_class), TC_HANDLE(1,0));
    rtnl_tc_set_handle(TC_CAST(fq_class), TC_HANDLE(1,1));
    if ((err = rtnl_tc_set_kind(TC_CAST(fq_class), "htb"))) {
            printf("Can not allocate HTB\n");
        exit (-1);
    }
    rtnl_htb_set_rate(fq_class, rate/8);
    // rtnl_htb_set_ceil(fq_class, 10e6);
    /* Submit request to kernel and wait for response */
    if ((err = rtnl_class_add(qdisc_sock, fq_class, NLM_F_CREATE))) {
        printf("Can not allocate HTB Class\n");
        return fq_class;
    }
    // rtnl_class_put(fq_class);
    return fq_class;
}
