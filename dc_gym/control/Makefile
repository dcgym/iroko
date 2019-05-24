CC=gcc
CFLAGS= -Wall -O3 -g
LFLAGS= -lnl-3 -lnl-route-3
QDISC=FQ
QDISC_LOWER = $(shell echo $(QDISC) | tr A-Z a-z)
DEPS = $(QDISC_LOWER).c raw_udp_socket.c raw_udp_socket.h
LIBNAME=libbw_control.so

all: bw_control node_control

node_control: node_controller.c ${DEPS}
	$(CC) $(CFLAGS) $< ${DEPS} -o node_control -I /usr/include/libnl3/ $(LFLAGS) -DQDISC_$(QDISC)

bw_control: bw_control.c ${DEPS}
	$(CC) $(CFLAGS) -fPIC -c raw_udp_socket.c -o raw_udp_socket.o $(LFLAGS)
	$(CC) $(CFLAGS) -fPIC -c $< -o bw_control.o $(LFLAGS)
	$(CC) $(CFLAGS) -shared bw_control.o raw_udp_socket.o -o $(LIBNAME)

clean:
	rm -rf loadgen *.o node_control
	rm -rf loadgen *.o bw_control

.PHONY: node_control bw_control
