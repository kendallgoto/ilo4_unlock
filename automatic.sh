#!/usr/bin/env bash
#
# This file is part of ilo4_unlock (https://github.com/kendallgoto/ilo4_unlock/).
# Copyright (c) 2022 Kendall Goto.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# NOTE: This code isn't necessarily safe! It's my personal notes for everything That
# I had to do to patch my server from a Ubuntu 21.10 Live CD on 2/20/2022.
# On a server, you can run this with
# wget https://raw.githubusercontent.com/kendallgoto/ilo4_unlock/main/automatic.sh && chmod +x automatic.sh && ./automatic.sh
set -e
sudo apt-add-repository -y universe
sudo apt update
sudo apt-get install -y python2-minimal git curl
curl https://bootstrap.pypa.io/pip/2.7/get-pip.py --output get-pip.py && sudo python2 get-pip.py
python2 -m pip install virtualenv
git clone --recurse-submodules https://github.com/kendallgoto/ilo4_unlock.git
cd ilo4_unlock
python2 -m virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
./build.sh init
./build.sh latest

sudo modprobe -r hpilo
mkdir -p flash
cp binaries/flash_ilo4 binaries/CP027911.xml flash/
cp build/ilo4_*.bin.patched flash/ilo4_250.bin

cd flash
cwd=$(pwd)

echo "Ready to flash! Run sudo ./flash_ilo4 --direct inside $CWD"
