CC=gcc
CFLAGS=-Wall -O3 -g
LFLAGS= -Wl,--as-needed -lnl-3 -lnl-route-3
LIBNAME=libqdisc_stats.so

all: qdisc_stats.c
	$(CC) $(CFLAGS) -fPIC -c $< -o qdisc_stats -I /usr/include/libnl3/ $(LFLAGS)
	$(CC) $(CFLAGS) -shared -o $(LIBNAME) qdisc_stats -lnl-3 -lnl-route-3

clean:
	rm -rf *.o .so qdisc_stats

