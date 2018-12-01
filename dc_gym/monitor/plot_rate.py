from helper import *

parser = argparse.ArgumentParser()
parser.add_argument('--files', '-f',
                    help="Rate timeseries output to one plot",
                    required=True,
                    action="store",
                    nargs='+',
                    dest="files")

parser.add_argument('--legend', '-l',
                    help="Legend to use if there are multiple plots.  File names used as default.",
                    action="store",
                    nargs="+",
                    default=None,
                    dest="legend")

parser.add_argument('--out', '-o',
                    help="Output png file for the plot.",
                    default=None, # Will show the plot
                    dest="out")

parser.add_argument('-s', '--summarise',
                    help="Summarise the time series plot (boxplot).  First 10 and last 10 values are ignored.",
                    default=False,
                    dest="summarise",
                    action="store_true")

parser.add_argument('--labels',
                    help="Labels for x-axis if summarising; defaults to file names",
                    required=False,
                    default=[],
                    nargs="+",
                    dest="labels")

parser.add_argument('--xlabel',
                    help="Custom label for x-axis",
                    required=False,
                    default=None,
                    dest="xlabel")

parser.add_argument('--ylabel',
                    help="Custom label for y-axis",
                    required=False,
                    default=None,
                    dest="ylabel")

parser.add_argument('-i',
                    help="Interfaces to plot (regex)",
                    default=".*",
                    dest="pat_iface")

parser.add_argument('--rx',
                    help="Plot receive rates on the interfaces.",
                    default=False,
                    action="store_true",
                    dest="rx")

parser.add_argument('--maxy',
                    help="Max mbps on y-axis..",
                    default=100,
                    action="store",
                    dest="maxy")

parser.add_argument('--miny',
                    help="Min mbps on y-axis..",
                    default=0,
                    action="store",
                    dest="miny")

parser.add_argument('--normalize',
                    help="normalise y-axis",
                    default=False,
                    action="store_true",
                    dest="normalise")

args = parser.parse_args()
if args.labels is None:
    args.labels = args.files

pat_iface = re.compile(args.pat_iface)

to_plot=[]
"""Output of bwm-ng csv has the following columns:
unix_timestamp;iface_name;bytes_out;bytes_in;bytes_total;packets_out;packets_in;packets_total;errors_out;errors_in
"""

if args.normalise and args.labels == []:
    raise "Labels required if summarising/normalising."
    sys.exit(-1)

bw = map(lambda e: int(e.replace('M','')), args.labels)
idx = 0

for f in args.files:
    data = read_list(f)
    #xaxis = map(float, col(0, data))
    #start_time = xaxis[0]
    #xaxis = map(lambda x: x - start_time, xaxis)
    #rate = map(float, col(2, data))
    rate = {}
    column = 2
    if args.rx:
        column = 3
    for row in data:
        try:
            ifname = row[1]
        except:
            break
        if ifname not in ['eth0', 'lo']:
            if not rate.has_key(ifname):
                rate[ifname] = []
            try:
                rate[ifname].append(float(row[column]) * 8.0 / (1 << 20))
            except:
                break

    if args.summarise:
        for k in rate.keys():
            if pat_iface.match(k):
                print k
                vals = filter(lambda e: e < 1500, rate[k][10:-10])
                if args.normalise:
                    vals = map(lambda e: e / bw[idx], vals)
                    idx += 1
                to_plot.append(vals)
    else:
        for k in sorted(rate.keys()):
            if pat_iface.match(k):
                print k
                plt.plot(rate[k], label=k)

plt.title("TX rates")
if args.rx:
    plt.title("RX rates")

if args.ylabel:
    plt.ylabel(args.ylabel)
elif args.normalise:
    plt.ylabel("Normalized BW")
else:
    plt.ylabel("Mbps")

plt.grid()
plt.legend()
plt.ylim((int(args.miny), int(args.maxy)))

if args.summarise:
    plt.boxplot(to_plot)
    plt.xticks(range(1, 1+len(args.files)), args.labels)

if not args.summarise:
    if args.xlabel:
        plt.xlabel(args.xlabel)
    else:
        plt.xlabel("Time")
    if args.legend:
        plt.legend(args.legend)

if args.out:
    plt.savefig(args.out)
else:
    plt.show()

