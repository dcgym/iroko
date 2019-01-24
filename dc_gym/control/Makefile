CC=gcc
CFLAGS=-Wall -O3 -g
LFLAGS=-pthread lnl-3 -lnl-route-3

all: node_controller.c
	$(CC) $(CFLAGS) $(LFLAGS) $< -o node_control -I /usr/include/libnl3/

clean:
	rm -rf loadgen *.o node_control

