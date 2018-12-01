import matplotlib.pyplot as plt


def colorGenerator():
    "Return cycling list of colors"
    colors = ['red', 'green', 'blue', 'orange', 'purple', 'cyan']
    index = 0
    while True:
        yield colors[index]
        index = (index + 1) % len(colors)


def markerGenerator():
    "Return cycling list of colors"
    markers = ['o', '^', 'v', '*', 'x', 'd']
    index = 0
    while True:
        yield markers[index]
        index = (index + 1) % len(markers)


def hatchGenerator():
    "Return cycling list of colors"
    hatches = ['/', '\\', '-', '.', '|', 'x']
    index = 0
    while True:
        yield hatches[index]
        index = (index + 1) % len(hatches)


def convertToStep(x, y):
    """Convert to a "stepped" data format by duplicating all but the last elt."""
    newx = []
    newy = []
    for i, d in enumerate(x):
        newx.append(d)
        newy.append(y[i])
        if i != len(x) - 1:
            newx.append(x[i + 1])
            newy.append(y[i])
    return newx, newy


def convertToStepUpCDF(x, y):
    """Convert to a "stepped" data format by duplicating all but the last elt.

    Step goes up, rather than to the right.
    """
    newx = []
    newy = []
    for i, d in enumerate(x):
        newx.append(d)
        newy.append(y[i])
        if i != len(x) - 1:
            newx.append(x[i])
            newy.append(y[i + 1])
    newx.append(newx[-1])
    newy.append(1.0)
    return newx, newy


def plotTimeSeries(data, title, xlabel, ylabel, step):
    """Plot a time series.

    Input: data, a list of dicts.
    Each inner-most dict includes the following fields:
        x: array
        y: array
        label: string

    step: if True, display data in stepped form.
    """
    fig = plt.figure()
    ax = plt.subplot(111)
    cgen = colorGenerator()
    colors = {}

    fig.canvas.set_window_title(title)

    for d in data:
        x = d['x']
        y = d['y']
        if step:
            x, y = convertToStep(x, y)
        plt.plot(x, y, label=d['label'], color=cgen.next())

    plt.xlabel(xlabel, fontsize=20)
    plt.ylabel(ylabel, fontsize=20)
    plt.grid(True)
    for tick in ax.xaxis.get_major_ticks():
        tick.label1.set_fontsize(18)
    for tick in ax.yaxis.get_major_ticks():
        tick.label1.set_fontsize(18)

    return fig


def plotCDF(data, title, xlabel, ylabel, step):
    data_mod = []
    for index, line in enumerate(data):
        vals = sorted(line['y'])
        x = sorted(vals)
        y = [(float(i) / len(x)) for i in range(len(x))]
        x, y = convertToStepUpCDF(x, y)
        entry = {}
        entry['x'] = x
        entry['y'] = y
        entry['label'] = line['label']
        data_mod.append(entry)

    return plotTimeSeries(data_mod, title, xlabel, ylabel, step=False)


if __name__ == '__main__':
    print convertToStep([1, 2, 3], [4, 5, 6])
