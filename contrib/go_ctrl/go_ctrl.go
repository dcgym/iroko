package main

import (
    "encoding/binary"
    "flag"
    "log"
    "os"
    "os/signal"
    "syscall"
    "github.com/google/gopacket"
    "github.com/google/gopacket/layers"
    "github.com/google/gopacket/pcap"
    "github.com/vishvananda/netlink"
)

var max_rate int


func ctrl_loop(qdisc *netlink.Fq, packetSource *gopacket.PacketSource, handle *pcap.Handle) error {
    for packet := range packetSource.Packets() {
        app := packet.ApplicationLayer()
        rate := binary.LittleEndian.Uint32(app.Payload())
        if err := change_qdisc(qdisc, rate); err != nil {
            return err
        }
        if err := send_response(handle, packet); err != nil {
            return err
        }
    }
    return nil
}

func send_response(handle *pcap.Handle, packet gopacket.Packet) error {
    if udplayer := packet.Layer(layers.LayerTypeUDP); udplayer != nil {
        udp := udplayer.(*layers.UDP)
        src_port := udp.SrcPort
        udp.SrcPort = udp.DstPort
        udp.DstPort = src_port
        if err := handle.WritePacketData(packet.Data()); err != nil {
            return err
        }
    }
    return nil
}

func change_qdisc(qdisc *netlink.Fq, rate uint32) error {
    qdisc.FlowMaxRate = rate / 8
    qdisc.Pacing = 1
    qdisc.InitialQuantum = (uint32(max_rate) / (8 * 10e6)) * 1500

    if err := netlink.QdiscChange(qdisc); err != nil {
        return err
    }
    return nil
}

func clean_all_qdiscs(ctrl_dev string) {
    link, err := netlink.LinkByName(ctrl_dev)
    if err != nil {
        log.Println(err)
    }
    qdiscs, err := netlink.QdiscList(link)
    if err != nil {
        log.Println(err)
    }
    if len(qdiscs) > 0 {
        for _, qdisc := range qdiscs {
            if err := netlink.QdiscDel(qdisc); err != nil {
                log.Println(err)
            }
        }
    }
}

func setup_qdisc(ctrl_dev string, rate uint32) (*netlink.Fq, error) {
    link, err := netlink.LinkByName(ctrl_dev)
    if err != nil {
        log.Println(err)
        return nil, err
    }
    qdisc := &netlink.Fq{
        QdiscAttrs: netlink.QdiscAttrs{
            LinkIndex: link.Attrs().Index,
            Handle:    netlink.MakeHandle(1, 0),
            Parent:    netlink.HANDLE_ROOT,
        },
        FlowMaxRate: uint32(max_rate) / 8,
        Pacing:      1,
        InitialQuantum: (uint32(max_rate) / (8 * 10e6)) * 1500,
    }
    if err := netlink.QdiscAdd(qdisc); err != nil {
        return nil, err
    }
    return qdisc, nil
}

func set_exit_handler(qdisc *netlink.Fq) {
    c := make(chan os.Signal, 2)
    signal.Notify(c, syscall.SIGINT, syscall.SIGTERM)
    go func() {
        <-c
        log.Println("Handling interrupt...")
        exit_handler(qdisc)
        os.Exit(0)
    }()
}

func exit_handler(qdisc *netlink.Fq) {
    if err := netlink.QdiscDel(qdisc); err != nil {
        log.Println(err)
    }
}

func main() {
    var net_dev string
    var ctrl_dev string
    flag.StringVar(&net_dev, "n", "",
        "the interface attached to the main network")
    flag.StringVar(&ctrl_dev, "c", "",
        "the interface attached to the control network")
    flag.IntVar(&max_rate, "r", 0,
        "the maximum allowed sending rate in bps")
    flag.Parse()
    if net_dev == "" || ctrl_dev == "" {
        flag.Usage()
        os.Exit(1)
    }

    clean_all_qdiscs(net_dev)
    qdisc, err := setup_qdisc(net_dev, uint32(max_rate));
    if err != nil {
        log.Println(err)
         os.Exit(1)
    }
    set_exit_handler(qdisc)

    handle, err := pcap.OpenLive(ctrl_dev, 1600, true, pcap.BlockForever)
    if err != nil {
        log.Println(err)
         os.Exit(1)
    }

    err = handle.SetBPFFilter("udp and port 20130")
    if err != nil {
        log.Println(err)
         os.Exit(1)
    }

    packetSource := gopacket.NewPacketSource(handle, handle.LinkType())
    if err := ctrl_loop(qdisc, packetSource, handle); err != nil {
        log.Println(err)
         os.Exit(1)
    }
    if err := netlink.QdiscDel(qdisc); err != nil {
        log.Println(err)
    }
}
