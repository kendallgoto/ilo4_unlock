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


# NOTE: this is just what I use on my system! I DON'T suggest these fan curves
# since they are aggressive and unsafe. I play loose since I'm lazy. Here's some setup notes:
# I write iLO directly to this system, running in a CentOS ESXI VM on my server
# I have this script loaded at boot with crontab @reboot
# I have a dnsmasq server on here to serve DHCP to the iLO on a private subnet (10.0.99.0)
# I have the iLO's password saved in /root/passwordfile and load it with sshpass
# I would rather do this via SSH keys, but I couldn't be bothered to get them working on the iLO.

# This setup is tuned for my DL380e Gen8 LFF server.
IP=10.0.99.50
PASSWD="/root/passwordfile"

sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan info'

sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan t 50 off'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan t 51 off'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan t 52 off'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan t 53 off'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan t 54 off'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan t 55 off'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan t 56 off'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan t 57 off'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan t 34 off'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan t 35 off'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan t 36 off'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan t 37 off'

#fix minimums
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan t 00 set 5'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan p 0 min 50'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan p 1 min 50'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan p 2 min 50'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan p 3 min 65'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan p 4 min 65'
sshpass -f "$PASSWD" ssh Administrator@${IP} 'fan p 5 min 65'
