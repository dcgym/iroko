CC=gcc
CFLAGS=-Wall -O3 -g
LFLAGS=-pthread

all: node_controller.c
	$(CC) $(CFLAGS) $(LFLAGS) $< -o node_control -I /usr/include/libnl3/ -lnl-genl-3 -lnl-3 -lnl-route-3

clean:
	rm -rf loadgen *.o node_control

