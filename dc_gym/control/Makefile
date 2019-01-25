CC=gcc
CFLAGS=-Wall -O3 -g
LFLAGS= -lnl-3 -lnl-route-3

all: node_controller.c
	$(CC) $(CFLAGS) $< -o node_control -I /usr/include/libnl3/ $(LFLAGS)

clean:
	rm -rf loadgen *.o node_control

