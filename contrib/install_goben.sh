#!/bin/bash

# exit when any command fails
set -e

GOARCH="$(dpkg --print-architecture)"
GO_SRC="go1.11.linux-${GOARCH}.tar.gz"
export GOPATH="$(pwd)/gopath"
export GOROOT="$(pwd)/go"
export PATH=${GOPATH}/bin:${GOROOT}/bin:${PATH}
GOBEN_BIN="${GOPATH}/bin/goben"

# wget https://dl.google.com/go/${GO_SRC}
# tar -xvf ${GO_SRC}
cd goben
go install ./goben
cd ..
mv ${GOPATH}/bin/goben $(pwd)/../dc_gym
chmod -R 775 ${GOPATH}
# rm -rf ${GO_SRC}
# rm -rf ${GOPATH}
# rm -rf ${GOROOT}