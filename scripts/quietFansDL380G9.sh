#!/bin/bash

# Used to solve the "Max fans because we decided to use a graphics card" bug. 
# Seems that just restarting using these commands is enough to return the fan behavior to normal. 
# Tested on DL380 Gen9

# Replace these values with those relevant to your iLO. Alternatively,
# consider defining them with environment variables.

IP=192.168.86.48
USER='Administrator'
PWD='pass'

sshpass -p $PWD ssh -oKexAlgorithms=+diffie-hellman-group14-sha1,diffie-hellman-group1-sha1 -oHostKeyAlgorithms=ssh-rsa,ssh-dss $USER@$IP 'fan g stop'
sshpass -p $PWD ssh -oKexAlgorithms=+diffie-hellman-group14-sha1,diffie-hellman-group1-sha1 -oHostKeyAlgorithms=ssh-rsa,ssh-dss $USER@$IP 'fan g start'


# The script can be triggered on startup with a crontab.
