# Iroko: The Data Center RL Gym
Iroko is an open source project that is focused on providing openAI compliant gyms. The aim is to develop machine learning algorithms that address data center problems and to fairly evaluate solutions again traditional techniques.

# Requirements
The data center emulator makes heavy uses of Linux tooling and its networking features. It operates most reliably on a recent Linux kernel (`4.15+`). The supported platform is Ubuntu (at least `16.04` is required). Using the emulator requires full sudo access.

# Package Dependencies
- `Clang` or `GCC` are required to build the traffic control managers.
- `git` for version control
- `bwn-ng` and `ifstat` to monitor traffic
- `python-pip` and `python3-pip` to install packages

# Python Dependencies
The generator supports both Python2 and Python3. Both `pip` and `pip3` can be used to install the packages.
- `numpy` for matrix operations
- `gym` to install openAI gym
- `ray`, `lz4`, and `opencv-python` to install the ray framework
- `seaborn` and `matplotlib` to generate plots

# Modules
- [Mininet](https://github.com/mininet/mininet) to build efficient and real network topologies
- [Goben](https://github.com/udhos/goben) to generate and measure traffic

# Installation
A convenient way to install the emulator is to run the `./install.sh`. It will install most dependencies locally via [Poetry](https://github.com/sdispater/poetry).

## Using OpenAI Benchmark
Currently a work in progress. In order to use the run\_benchmark.py script, you need to also follow the installation set-up for the [Open AI Benchmark](https://github.com/openai/baselines) project and need to run the script with python 3.5.  
