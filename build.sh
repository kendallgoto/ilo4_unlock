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
if [ $# -ne 1 ]; then
    echo "usage: $0 <init|250|273|277>"
    exit 1
fi
set -e

check_hash() {
	HASH=`sha1sum "$1" | cut -d' ' -f1`
	KNOWN_HASH=`cat $2`
	if [ "$HASH" != "$KNOWN_HASH" ]; then
		echo "Binary hash mismatch ... please init again."
		exit 1
	fi
}
run_patch() {
	echo "Patching with iLO $1"
	USE_FILE="binaries/ilo4_$1.bin"
	PATCH_PATH="patches/$1"
	check_hash "$USE_FILE" "$PATCH_PATH/initial.sha1"

	./$PATCH_PATH/build.sh "$USE_FILE" "build"

	check_hash "build/ilo4_$1.bin.patched" "$PATCH_PATH/checksum.sha1"
	exit 0
}
do_init() {
	echo "Downloading binaries ..."
	rm -rf binaries/
	mkdir -p binaries/
	for d in patches/* ; do
		if [ -d "$d" ]; then
			SHORT_NAME=`basename $d`
			BIN_URL=`cat $d/bin-link.url`
			FILE_NAME="ilo4_$SHORT_NAME.bin"
			echo "Downloading $BIN_URL as $FILE_NAME"
			wget -O temp.csexe -q $BIN_URL
			sh temp.csexe --unpack=archivetemp > /dev/null
			cp archivetemp/ilo4_*.bin ./binaries/
			if [ "$SHORT_NAME" = "250" ]; then
				cp archivetemp/flash_ilo4 archivetemp/CP027911.xml ./binaries/
			fi
			rm -rf archivetemp
			rm temp.csexe
		fi
	done
	echo "Downloaded binaries to binaries/*.bin"
	ls -al binaries
	exit 0
}

cd "${0%/*}" # cd to script location

case $1 in

	init)
		do_init
;;
	"250" | "273" | "277")
		run_patch $1
;;
	*)
		echo "usage: $0 <init|250|273|277>"
	    exit 1
esac
