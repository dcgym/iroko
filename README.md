# Iroko: The Data Center RL Gym
DISCLAIMER: This project is still very early stage research. It is not stable, well tested, and changes quickly. If you want to use this project, be warned.

Iroko is an open source project that is focused on providing openAI compliant gyms. The aim is to develop machine learning algorithms that address data center problems and to fairly evaluate solutions again traditional techniques.

A more concrete description is available in our [short paper](https://arxiv.org/abs/1812.09975).

# Requirements
The data center emulator makes heavy uses of Linux tooling and its networking features. It operates most reliably on a recent Linux kernel (`4.15+`). The supported platform is Ubuntu (at least `16.04` is required). Using the emulator requires full sudo access.

# Package Dependencies
- `GCC` or `Clang` and the `build-essentials` are required.
- `git` for version control
- `libnl-route-3-dev` to compile the traffic managers
- `bwn-ng` and `ifstat` to monitor traffic
- `python` and `python-setuptools` to build Python packages and run the emulator

## Python Dependencies
The generator supports both Python2 and Python3. `pip` and `pip3` can be used to install the packages.

- `numpy` for matrix operations
- `gym` to install openAI gym
- `seaborn` and `matplotlib` to generate plots

## Mininet Dependencies
The datacenter networks are emulated using [Mininet](https://github.com/mininet/mininet). At minimum Mininet requires the installation of
- `openvswitch-switch`, `cgroup-bin`, `help2man`

## Ray Dependencies
The emulator uses [Ray](https://github.com/ray-project/ray) to implement and evaluate reinforcement learning algorithms. Ray's dependencies include:
- `tensorflow`, `setproctitle`, `psutil`, `opencv-python`

## Goben Dependencies
The emulator generates and measures traffic using [Goben](https://github.com/udhos/goben). While an amd64 binary is already provided in the repository, the generator submodule can also be compiled using `Go 1.11`. The `contrib/` folder contains a script to install Goben locally.

# Installation
A convenient, self-contained way to install the emulator is to run the `./install.sh`. It will install most dependencies locally via [Poetry](https://github.com/sdispater/poetry).