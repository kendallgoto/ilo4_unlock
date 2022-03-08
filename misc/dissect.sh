#!/usr/bin/env bash
#
# This file is part of the ilo4_unlock (https://github.com/kendallgoto/ilo4_unlock/).
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
set -e

cd "${0%/*}" # cd to script location
cd ../
cp build/elf.bin.patched ilo4_toolbox/scripts/iLO4/elf.bin
cd ilo4_toolbox/scripts/iLO4/
rm -rf mods loaders scripts
ruby dissection.rb elf.bin
zip -r dissect.zip mods loaders scripts
cd ../../../
cp ilo4_toolbox/scripts/iLO4/dissect.zip build/dissect.zip
