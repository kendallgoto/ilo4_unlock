#!/bin/bash

# Variables
ilo_user="#"          # Replace with your iLO username
ilo_pass="#"          # Replace with your iLO password
ilo_host="#"          # Replace with your iLO hostname or IP address

# Options to enable older key exchange and host key methods
ssh_options="-o KexAlgorithms=diffie-hellman-group14-sha1,diffie-hellman-group1-sha1 -o HostKeyAlgorithms=ssh-rsa,ssh-dss -o StrictHostKeyChecking=no"

# Loop through the sensor numbers and send the command
for sensor in {01..46} #set lo 1600 to all sensors (in my case 46 sensors) 
do
    sshpass -p $ilo_pass ssh $ssh_options $ilo_user@$ilo_host "fan pid $sensor lo 1600"
done
