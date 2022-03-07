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
if [ $# -ne 2 ]; then
    echo "usage: $0 <firmware.bin> <build-dir>"
    exit 1
fi

ROOT_DIR=`git rev-parse --show-toplevel`
SCRIPT_DIR="$ROOT_DIR/ilo4_toolbox/scripts/iLO4"
UTIL_DIR="$ROOT_DIR/util"
BUILD_LOC=$(realpath "$2")
DIR=`dirname $0`
FIRMWARE="$1"
DEST="$BUILD_LOC/$(basename "$FIRMWARE").patched"

rm -rf "$BUILD_LOC"

echo "Starting iLO4 Toolbox Extraction ..."
python "$SCRIPT_DIR/ilo4_extract.py" "$FIRMWARE" "$BUILD_LOC"
echo "Patching bootloader ..."
python "$UTIL_DIR/patch.py" "$BUILD_LOC/bootloader.bin" "$DIR/patch_bootloader.json" "$BUILD_LOC/bootloader.bin.patched"
echo "Patching kernel ..."
python "$UTIL_DIR/patch.py" "$BUILD_LOC/kernel_main.bin" "$DIR/patch_kernel.json" "$BUILD_LOC/kernel_main.bin.patched"
echo "Patching userland ..."
python "$UTIL_DIR/patch.py" "$BUILD_LOC/elf.bin" "$DIR/patch_userland.json" "$BUILD_LOC/elf.bin.patched"

echo "Repacking with iLO4 Toolbox ..."
python "$SCRIPT_DIR/ilo4_repack.py" "$FIRMWARE" "$BUILD_LOC/firmware.map" "$BUILD_LOC/elf.bin.patched" "$BUILD_LOC/kernel_main.bin.patched" "$BUILD_LOC/bootloader.bin.patched"
mv "$FIRMWARE.backdoored.toflash" "$DEST"

echo "Final firmware at $2/$(basename "$DEST")"
