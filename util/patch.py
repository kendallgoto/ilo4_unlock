#!/usr/bin/env python
#
# This file is part of ilo4_unlock (https://github.com/kendallgoto/ilo4_unlock/).
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
from keystone import *
def read_patch(file):
    dir = os.path.dirname(sys.argv[2])
    patch = os.path.join(dir, "asm", file)

    with open(patch, "rb") as f:
        handler = f.read()
        # remove comments ...
        handler_split = handler.split('\n')
        for i in range(len(handler_split)):
            this_line = handler_split[i]
            this_line = this_line.split(";")[0]
            handler_split[i] = this_line
        handler = "\n".join(handler_split)
        print handler
        ks = Ks(KS_ARCH_ARM, KS_MODE_ARM)
        try:
            output = ks.asm(handler)
        except KsError as e:
            print "Error with Keystone ", e.message
            if e.get_asm_count() is not None:
                print "asmcount = %u" % e.get_asm_count()
            sys.exit(1)
        return ''.join(chr(x) for x in output[0])


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
    if "file" in patch:
        patch["patch"] = read_patch(patch["file"])
        patch["noDecode"] = True
    if "noDecode" in patch:
        patch_data = patch["patch"]
    else:
        patch_data = ("".join(patch["patch"].split())).decode("hex")
    realsize = sys.getsizeof(patch_data) - sys.getsizeof('')
    print ilo4.hexdump(check_data)
    print ilo4.hexdump(patch_data)
    if realsize != size:
        print "Patch length (%d) does not match replaced size (%d)" % (realsize, size)
        sys.exit(1)
    data = data[:offs] + patch_data + data[endOffs:]

data = data
with open(sys.argv[3], "wb") as f:
    f.write(data)
