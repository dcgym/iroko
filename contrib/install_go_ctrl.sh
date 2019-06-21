#!/bin/bash

# exit when any command fails
set -e

GOARCH="$(dpkg --print-architecture)"
GO_SRC="go1.12.linux-${GOARCH}.tar.gz"
export GOPATH="$(pwd)/gopath"
export GOROOT="$(pwd)/go"
export PATH=${GOPATH}/bin:${GOROOT}/bin:${PATH}
BIN="$(pwd)/go_ctrl/go_ctrl"

wget https://dl.google.com/go/${GO_SRC}
tar -xvf ${GO_SRC}
cd go_ctrl
go build
cd ..
chmod 775 ${BIN}
mv ${BIN} $(pwd)/../dc_gym/control
chmod -R 775 ${GOPATH}
rm -rf ${GO_SRC}
rm -rf ${GOPATH}
rm -rf ${GOROOT}