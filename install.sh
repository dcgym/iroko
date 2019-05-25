#!/bin/bash

# exit when any command fails
set -e

# fetch submodules
git submodule update --init --recursive

# Install essential dependencies
sudo apt install -y build-essential

# Install Python dependencies
sudo apt install -y python3           # default ubuntu python3.x
sudo apt install -y python3-venv      # support Python virtual environments
sudo apt install -y python3-dev       # for python3.x installs
sudo apt install python3-setuptools   # required to install pip


# install Mininet dependencies
sudo apt install -y openvswitch-switch
sudo apt install -y cgroup-bin
sudo apt install -y help2man
# install Mininet
cd contrib/mininet
sudo make install PYTHON=python3    # install the Python3 version
cd ../..

# install traffic monitors
sudo apt install -y tcpdump
sudo apt install -y ifstat

# install the traffic generator using Go
if  [[ $1 = "--goben" ]]; then
echo "Building goben traffic generator..."
cd contrib
./install_goben.sh
cd ..
fi


# install the PCC kernel module
if  [[ $1 = "--pcc" ]]; then
make -C contrib/pcc/src/
cp contrib/pcc/src/tcp_pcc.ko dc_gym/topos
fi

# required for traffic adjustment
sudo apt install -y libnl-route-3-dev

# Build the dc_gym
curl -sSL https://raw.githubusercontent.com/sdispater/poetry/master/get-poetry.py | python
source $HOME/.poetry/env
poetry self:update            # Update Poetry
# poetry cache:clear . --all    # Clear Poetry cache
poetry update                 # Update Poetry lock dependencies
poetry install                # Package the dc_gym
poetry build                  # Build distribution package

# compile the traffic control
make -C dc_gym/monitor
make -C dc_gym/control

# Install pip locally
export PATH+=$PATH:~/.local/bin
wget https://bootstrap.pypa.io/get-pip.py
python3 get-pip.py --user
rm get-pip.py

# Install the dc_gym locally
pip3 install --upgrade --user dist/*.whl

# Get the correct Python version
PYTHON3_VERSION=`python3 -c 'import sys; version=sys.version_info[:3]; print("{0}{1}".format(*version))'`

# Install the latest ray build for Python 2 and 3
pip3 install --user -U https://s3-us-west-2.amazonaws.com/ray-wheels/latest/ray-0.8.0.dev0-cp${PYTHON3_VERSION}-cp${PYTHON3_VERSION}m-manylinux1_x86_64.whl

# Install unresolved Ray runtime dependencies...
sudo apt install -y libsm6 libxext6 libxrender-dev