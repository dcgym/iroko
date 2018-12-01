'''
Plot CPU utilization of each virtual host.
'''

from helper import *

parser = argparse.ArgumentParser("Plot stacked bar chart of CPU usage")
parser.add_argument('--files', '-f',
                    help="File to read CPU usage from.",
                    required=True,
                    nargs="+",
                    dest="files")

parser.add_argument('--out', '-o',
                    help="Output png for plot",
                    default=None,
                    dest="out")

parser.add_argument('-s', '--summarise',
                    help="Summarise the time series plot (boxplot).  First 10 and last 10 values are ignored.",
                    default=False,
                    dest="summarise",
                    action="store_true")

parser.add_argument('--labels', '-l',
                    help="Labels for x-axis if summarising; defaults to file names",
                    required=False,
                    default=None,
                    nargs="+",
                    dest="labels")

args = parser.parse_args()
if args.labels is None:
	args.labels = args.files

def aggregate(data):
	"""Aggregates to give a total cpu usage"""
	data = map(list, data)
	return map(sum, zip(*data))

def plot_series():
	data = parse_cpu_usage(args.files[0])
	N = len(data)
	data = transpose(data)
	ind = range(N)
	width=1
	colours = ['y','g','r','b','purple','brown','cyan']
	legend = "user,system,nice,iowait,hirq,sirq,steal".split(',')
	nfields = 7
	legend = legend[0:nfields]
	p = [0]*nfields
	bottom = [0]*N

	plt.ylabel("CPU %")
	plt.xlabel("Seconds")
	for i in xrange(nfields):
	    p[i] = plt.bar(ind[0:N], data[i], width, bottom=bottom, color=colours[i]) 
	    for j in xrange(N):
	        bottom[j] += data[i][j]
	plt.legend(map(lambda e: e[0], p), legend)

def plot_summary():
	plt.ylabel("CPU %")
	to_plot=[]
	for f in args.files:
		data = parse_cpu_usage(f)
		N = len(data)
		data = transpose(data)
		ind = range(N)
		data = aggregate(data)
		to_plot.append(data[10:-10])
	plots = plt.boxplot(to_plot)
	plt.yticks(range(0,110,10))
	plt.title("CPU utilisation")
	plt.grid()
	plt.xticks(range(1, 1+len(args.files)), args.labels)

if args.summarise:
	plot_summary()
else:
	plot_series()

if args.out is None:
    plt.show()
else:
    plt.savefig(args.out)

