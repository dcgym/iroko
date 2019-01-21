#!/bin/bash

# fetch submodules
git submodule update --init --recursive

# # install mininet
cd contrib/mininet
sudo -E util/install.sh -nv
cd ../..


# traffic monitors
sudo apt install -y bwm-ng
sudo apt install -y ifstat

# compile the traffic control
make -C dc_gym/cluster_loadgen
make -C dc_gym/control

# Install Python
sudo apt install -y python            # default ubuntu python2.x
sudo apt install -y python3           # default ubuntu python3.x
sudo apt install -y python-dev        # for python2.x installs
sudo apt install -y python3-dev       # for python3.x installs
sudo apt install -y python3-distutils # required to install pip

# Install pip locally
export PATH+=$PATH:~/.local/bin
wget https://bootstrap.pypa.io/get-pip.py
python3 get-pip.py --user
python get-pip.py --user
rm get-pip.py

# Get the correct Python version
PYTHON_VERSION=`python -c 'import sys; version=sys.version_info[:3]; print("{0}{1}".format(*version))'`
PYTHON3_VERSION=`python3 -c 'import sys; version=sys.version_info[:3]; print("{0}{1}".format(*version))'`

# Build the dc_gym
curl -sSL https://raw.githubusercontent.com/sdispater/poetry/master/get-poetry.py | python
source $HOME/.poetry/env
poetry self:update  # Update Poetry
poetry update       # Update poetry lock dependencies
poetry install      # Package the dc_gym
poetry build        # Build distribution package

# Install the dc_gym locally
pip install --user dist/*.whl
pip3 install --user dist/*.whl

# Install the latest ray build for python 2.7
pip install --user -U https://s3-us-west-2.amazonaws.com/ray-wheels/latest/ray-0.6.2-cp${PYTHON_VERSION}-cp${PYTHON_VERSION}mu-manylinux1_x86_64.whl
pip3 install --user -U https://s3-us-west-2.amazonaws.com/ray-wheels/latest/ray-0.6.2-cp${PYTHON3_VERSION}-cp${PYTHON3_VERSION}m-manylinux1_x86_64.whl

# Install unresolved Ray dependencies...
pip install --user psutil
pip3 install --user psutil

