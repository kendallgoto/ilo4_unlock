#!/usr/bin/env python
#
# This file is part of the ilo4_unlock (https://github.com/kendallgoto/ilo4_unlock/).
# Copyright (c) 2022 Kendall Goto
# with some code derived from https://github.com/airbus-seclab/ilo4_toolbox
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

import sys
import json
import imp
import os
dirname = os.path.dirname(__file__)
ilo4 = imp.load_source('ilo4', os.path.join(dirname, '../ilo4_toolbox/scripts/iLO4/ilo4lib.py'))

if len(sys.argv) < 4:
    print "usage: %s <input-file.bin> <patch-file.json> <result-file.bin.patched>" % sys.argv[0]
    sys.exit(1)

with open(sys.argv[1], "rb") as f:
    data = f.read()

with open(sys.argv[2], "rb") as f:
    patches = json.load(f)

for patch in patches:
    print "Applying patch, \"%s\"" % patch["remark"]

    offs = int(patch["offset"], 0)
    size = patch["size"]
    endOffs = offs+size
    check_data = data[offs:endOffs]
    if "prev_data" in patch:
        if "noDecode" in patch:
            prev_data = patch["prev_data"]
        else:
            prev_data = ("".join(patch["prev_data"].split())).decode("hex")
        if check_data != prev_data:
            print ilo4.hexdump(prev_data)
            print ilo4.hexdump(check_data)
            print "[-] Error, bad file content at offset %x" % offs
            sys.exit(1)

    if "noDecode" in patch:
        patch_data = patch["patch"]
    else:
        patch_data = ("".join(patch["patch"].split())).decode("hex")
    print ilo4.hexdump(check_data)
    print ilo4.hexdump(patch_data)
    data = data[:offs] + patch_data + data[endOffs:]

data = data
with open(sys.argv[3], "wb") as f:
    f.write(data)
