#!/bin/bash


# This was made using bits of ja-silence-dl20G9.sh code and inspired by other bits here and there.
# At first, I heavily modified cf-dynamic-fans to match my setup and include a logarithmic curve for the fans,
# it worked great, but the issue was that I did not trust relying on a bash script to control the maximum fan speed.
# Relying on such a high-level utility to control something as important as the temperature seemed a bit dangerous.
# So I looked at the fan info, read a bit and started to understand what was faulty in HPE's algorithms.
# I ended up with what I believe to be a "safe" solution for my setup, since it does not modify any fan maximum
# and more importantly, does not rely on any high-level running process
# As a result, the fans can and will ramp up according to the readings, which are not modified
# I only lower the minimum limit and increase some faulty (I believe) low setpoints



### CONFIG GOES HERE
IP=192.168.1.120
SCREEN_NAME=iLO4fansession
SSH_USER=fanctrl # You should set up a different user than Administrator in iLO, no extra permissions are needed for the user.
SSH_KEY=/etc/ssh/id_fanctrl # Set to the location of the SSH key for the above user.

PID_NUMBER=52  # Set here the number of PIDs that fan info reports in the algorithms table.
MIN_SPEED=2550 # Set the minimum speed the fans can run at (format is XX.XX°C = XXXX)
### END CONFIG


# To prevent bash from complaining about the locale in some cases where numeric locale uses a comma
export LC_NUMERIC="C"

# Check if iLO IP is up
while :; do
    echo -e "Checking if ${IP} is up."
    ping -q -c 1 ${IP} &>/dev/null
    if [ $? -ne 0 ]; then
            echo "iLO is not responding. Reattempting in 30 seconds.";
    else
            break
    fi
    sleep 30
done


# Initiate iLO session :
if ! screen -list | grep -q "$SCREEN_NAME"; then
        IP=${IP} screen -dmS $SCREEN_NAME
        echo -e "Establishing SSH session inside screen."


        screen -S $SCREEN_NAME -X stuff "ssh -i ${SSH_KEY} -t  ${SSH_USER}@${IP} -o PubKeyAcceptedKeyTypes=+ssh-rsa -o HostKeyAlgorithms=+ssh-dss -o KexAlgorithms=+diffie-hellman-group14-sha1 -o LocalCommand='fan info'"`echo -ne '\015'`
        # `echo -ne '\015'` emulates pressing the Enter key.

        # Wait
        echo -e "Sleeping for 5 seconds."
        sleep 5
        # Stop waiting :o)
        echo -e "Resuming fan commands."
else
        echo "Found screen session $SCREEN_NAME"
fi

# Set minimum speed for the fans
for ((i=1;i<=PID_NUMBER;i++)); do
        screen -S $SCREEN_NAME -X stuff "fan pid $i lo $MIN_SPEED"`echo -ne '\015'`
        sleep .2
        # Sleep for 200ms, because iLO is slow and sometimes skips commands
done

MIN_SPEED_ADJ=$(printf "%.1f\n" $(echo "$MIN_SPEED/100" | bc -l))
for ((i=0;i<=7;i++)); do
        screen -S $SCREEN_NAME -X stuff "fan p $i min $MIN_SPEED_ADJ"`echo -ne '\015'`
        sleep .2
done

REAL_SPEED=$(printf "%.1f\n" $(echo "($MIN_SPEED/25500)*100" | bc -l))
echo -e "Minimum fan speed set to $REAL_SPEED%"

# Set here the correction for faulty PID temperatures which cause the fans to start ramping up too soon
# For me, the setpoint for PID 50 (whatever that is) was 36°C ! And the setpoint for pid 35 (PCI-2 Zone) was 40°C
# To keep things safe, take notice of the Caution and Critical temperatures in fan info.
# You might want to ignore some faulty readings too if you have non-HP stuff, I don't know much about that, my setup is pretty stock.
# (proprietary software/hardware sucks)

screen -S $SCREEN_NAME -X stuff "fan pid 50 sp 5500"`echo -ne '\015'` # No Caut nor Crit info, but I guess 55°C is fine
sleep .2
screen -S $SCREEN_NAME -X stuff "fan pid 35 sp 5200"`echo -ne '\015'` # Caut was 65°C and Crit was 70°C
echo -e "Corrected faulty setpoints"
