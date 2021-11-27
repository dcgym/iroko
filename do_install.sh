#!/bin/bash

# Exit when any command fails
set -e
# Make verbose
set -x

# fetch submodules at their latest version
git submodule update --init --recursive

# Install essential dependencies
sudo apt install -y build-essential
sudo apt install -y curl
sudo apt-get install --reinstall python3-pkg-resources

# Install Python dependencies
sudo apt install -y python3             # default ubuntu python3.x
sudo apt install -y python3-venv        # support Python virtual environments
sudo apt install -y python3-dev         # for python3.x installs
sudo apt install -y python3-setuptools  # unfortunately required for poetry
# Get the correct Python version
PYTHON3_VERSION=`python3 -c 'import sys; version=sys.version_info[:3]; print("{0}{1}".format(*version))'`

if [ "$PYTHON3_VERSION" -lt "36" ]; then
    echo "\nPython version lower than 3.6! Installing 3.6...\n"
    sudo apt install -y python3.6;
    sudo apt install -y python3.6-venv;
    sudo apt install -y python3.6-dev;
    PYTHON3_CMD="python3.6";
    PYTHON3_VERSION="36";
    PIP_VERSION="pip3.6"
else
    PYTHON3_CMD="python3";
    PIP_VERSION="pip3"
fi

# install Mininet dependencies
sudo apt install -y openvswitch-switch cgroup-tools help2man
# install Mininet
cd contrib/mininet
sudo make install PYTHON=$PYTHON3_CMD    # install the Python3 version
cd ../..

# install traffic monitors
sudo apt install -y tcpdump ifstat

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

# Install pip locally
export PATH+=$PATH:~/.local/bin
wget https://bootstrap.pypa.io/get-pip.py
$PYTHON3_CMD get-pip.py --user
rm get-pip.py

# Build the dc_gym
curl -sSL https://install.python-poetry.org | $PYTHON3_CMD -
yes | poetry cache clear --all .  # Clear Poetry cache, this is sometimes needed
rm -rf poetry.lock                # # Bugfix for repeated install
rm -rf dist                       # Bugfix for repeated install
poetry update                     # Update Poetry lock dependencies
poetry install                    # Package the dc_gym
poetry build                      # Build distribution package

# Install the dc_gym locally
$PIP_VERSION install --upgrade --user dist/*.whl

# compile the traffic control
make -C dc_gym/monitor
make -C dc_gym/control

# Install the latest ray build for $PYTHON3_CMD and 3
# $PIP_VERSION install --user -U https://s3-us-west-2.amazonaws.com/ray-wheels/latest/ray-0.9.0.dev0-cp${PYTHON3_VERSION}-cp${PYTHON3_VERSION}m-manylinux1_x86_64.whl

# Install unresolved Ray runtime dependencies...
sudo apt install -y libsm6 libxext6 libxrender-dev
