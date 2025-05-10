#!/usr/bin/env bash
#
# This file is part of ilo4_unlock (https://github.com/kendallgoto/ilo4_unlock/).
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

source /home/python/venv/bin/activate
set -e

if [ "$#" -eq 0 ]; then
    /app/build.sh init
    /app/build.sh latest
    exit 1
fi

/app/build.sh "$@"
