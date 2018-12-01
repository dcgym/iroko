CC=gcc
CFLAGS=-Wall -O3 -g
LFLAGS=-pthread

all: node_controller.c
	$(CC) $(CFLAGS) $(LFLAGS) $< -o node_control

clean:
	rm -rf loadgen *.o node_control

