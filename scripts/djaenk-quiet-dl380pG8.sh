#!/bin/bash

# I use this on my DL380p Gen8 running Proxmox VE 7.2.
# The server has two of its eight SFF bays populated and is otherwise stock.
# I consider this a safer solution than explicitly disabling sensors or
# throttling fans because it reduces the minimum fan speed for an overreactive
# sensor while keeping all other fan curves. I wouldn't say this silences the
# server, but it does make it magnitudes quieter. Referenced from
# https://www.reddit.com/r/homelab/comments/di3vrk/silence_of_the_fans_controlling_hp_server_fans/firx6op/

# Replace these values with those relevant to your iLO. Alternatively,
# consider defining them with environment variables.

IP=x.x.x.x
USER='Administrator'
PWD='password'
OPT='-oKexAlgorithms=+diffie-hellman-group14-sha1'

sshpass -p $PWD ssh ${OPT} $USER@$IP 'fan info'
sshpass -p $PWD ssh ${OPT} $USER@$IP 'fan pid 47 lo 1600'

# The script can be triggered on startup with a crontab.
# While writing the cron job, a one liner can be used instead:
# @reboot sshpass -p password ssh -oKexAlgorithms=+diffie-hellman-group14-sha1 Administrator@x.x.x.x 'fan pid 47 lo 1600'
