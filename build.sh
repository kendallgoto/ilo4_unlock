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
exit_help() {
    echo "usage: \"$0 <init/latest/patch-name>\""
    echo "       \"$0 init\" to download binaries on a new install"
    echo "       \"$0 latest\" to automatically build the latest target"
    echo "       \"$0 [patch-name]\" to directly build a patch from patches/"
    exit 1
}
check_hash() {
	HASH=`sha1sum "$1" | cut -d' ' -f1`
	if [ "$HASH" != "$2" ]; then
		echo "Binary hash mismatch ... please init again."
		exit 1
	fi
    echo "Hash validated for $1"
}
run_patch() {
    PATCH_PATH="patches/$1"
    if [ -f "$PATCH_PATH/config" ]; then
        source "$PATCH_PATH/config"
        BIN_PATH="binaries/$BINARY_NAME"
        check_hash "$BIN_PATH" "$BINARY_SHA1"
        ./$PATCH_PATH/build.sh "$BIN_PATH" "build"
        check_hash "build/$BINARY_NAME.patched" "$RESULT_SHA1"
        exit 0
    else
        exit_help
    fi
}
do_init() {
	echo "Downloading binaries ..."
	rm -rf binaries/
	mkdir -p binaries/
	for d in patches/* ; do
		if [ -d "$d" ]; then
            if [ -f "$d/config" ]; then
                source "$d/config"
                if [ -f "./binaries/$BINARY_NAME" ]; then
                    echo "Binary $BINARY_NAME already downloaded ..."
                else
                    echo "Downloading $BINARY_URL as $BINARY_NAME"
                    wget -O temp.csexe -q $BINARY_URL
                    sh temp.csexe --unpack=archivetemp > /dev/null
                    cp archivetemp/ilo4_*.bin "./binaries/$BINARY_NAME"
                    if [ "$NAME" = "250" ]; then
                        cp archivetemp/flash_ilo4 archivetemp/CP027911.xml ./binaries/
                    fi
                    rm -rf archivetemp
                    rm temp.csexe
                    check_hash "binaries/$BINARY_NAME" "$BINARY_SHA1"
                fi
            fi
		fi
	done
	echo "Downloaded binaries to to ./binaries"
	ls -al binaries
	exit 0
}
get_latest() {
    latest_patch=`cat ./patches/latest`
    run_patch $latest_patch
}

# Runtime
if [ $# -ne 1 ]; then
    exit_help
fi
set -e


cd "${0%/*}" # cd to script location

case $1 in
	init)
		do_init
;;
    "latest")
        get_latest
;;
	*)
		run_patch $1
;;
esac
