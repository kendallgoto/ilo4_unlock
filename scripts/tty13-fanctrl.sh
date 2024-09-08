#!/usr/bin/env bash
#
# This was made using caffeineflo's cf-dynamic-fans.sh and jazinheira's ja-silence-dl20G9.sh (itself based on aterfax-silence-dl380pG8-screen.sh)
#
# This setup is tuned for my DL360p Gen 8 server with only one CPU.
#
# We establish a screen session, SSH to iLO4 and "stuff" it with commands.
# This preserves the first TTY in the screen session connected with iLO4
# so further command input/output can be visualised.
# We're avoiding the "output only goes in the first SSH session/TTY" bug!
#
# SSH is using SSH keys to connect in this example. Generate a key then add in iLO.
#
# This script adjusts the fan speed based on the highest temperature, ignoring the HD Controller which gets way hotter than the rest of the components on idle.
# The controller has a rather high tolerance (110 Critical in iLO) so it should not be a problem, but I included a failsafe just in case it gets too hot
# There could be potential benefits using a small USB/SATA powered fan on top of the controller's heat sink.
#
# I modified caffeineflo's temperature growth formula to include a logarithmic curve version (exponential speed growth), keeping the fans quiet under no significant load in my homelab.
# The output includes info to compare both speeds, I found it's much more quiet in most cases
#
# The script can be activated by a .service unit and will run every 30 seconds
# Rename this to fanctrl and put it in /usr/local/bin
#
# Required packages: freeipmi, lm-sensors, jq, screen, bc
# freeipmi might need additional configuration if the os you're executing this on isn't the same as the server you're trying to control.

# Example .service unit:
#[Unit]
#Description=Adjust fan speed
#
#[Service]
#Type=simple
#ExecStart=/usr/local/bin/fanctrl -l
#Restart=on-failure
#RestartSec=5s
#SendSIGKILL=no
#
#[Install]
#WantedBy=multi-user.target


### CONFIG GOES HERE :
IP=192.168.0.120
SCREEN_NAME=iLO4fansession
SSH_USER=fanctrl # You should set up a different user than Administrator in iLO, no extra permissions are needed for the user.
SSH_KEY=/etc/ssh/id_fanctrl # Set to the location of the SSH key for the above user.

FAN_GROUP="0 1 2 3 4 5 6 7"  # Define fan groups based on your setup
HD_ID=50  # Change if it does not correspond to your HD Controller (run ipmi-sensors to find out, sensor 31 on iLO is 50 for me in ipmi-sensors)

MIN_TEMP=45
MIN_TEMP_LOG=45
MAX_TEMP=67
HD_MAX=88 # This is the failsafe HD Controller temperature at which the fans spin faster.

MIN_SPEED=40
MIN_SPEED_LOG=40
MAX_SPEED=255
TEMP_RANGE=$((MAX_TEMP - MIN_TEMP))  # 22
SPEED_RANGE=$((MAX_SPEED - MIN_SPEED))  # 215
### END CONFIG

# Only one of me should be running :
if ! pgrep -x fanctrl > /dev/null
then

#This avoid setting a systemd timer unit and lets the script itself handle the loop (systemd kills child processes
while :
do

# Initiate SSH session to iLO
if ! screen -list | grep -q "$SCREEN_NAME"; then

    IP=${IP} screen -dmS $SCREEN_NAME

    echo -e "Establishing SSH session inside screen."

    while [ true ]
    do
            echo -e "Checking if ${IP} is up."
            ping -q -c 1 ${IP} &>/dev/null
            if [ $? -ne 0 ]; then
                    echo "iLO is not responding. Reattempting in 30 seconds.";
            else
                    break
            fi
            sleep 30
    done

    screen -S $SCREEN_NAME -X stuff "ssh -i ${SSH_KEY} -t  ${SSH_USER}@${IP} -o PubKeyAcceptedKeyTypes=+ssh-rsa -o HostKeyAlgorithms=+ssh-dss -o KexAlgorithms=+diffie-hellman-group14-sha1 -o LocalCommand='fan info'"`echo -ne '\015'`

    echo -e "Sleeping for 5 seconds."
    sleep 5

    echo -e "Resuming fan commands."

    # `echo -ne '\015'` emulates pressing the Enter key.

    # Set fan minimums.
    screen -S $SCREEN_NAME -X stuff 'fan p 0 min 25'`echo -ne '\015'`
    screen -S $SCREEN_NAME -X stuff 'fan p 1 min 25'`echo -ne '\015'`
    screen -S $SCREEN_NAME -X stuff 'fan p 2 min 25'`echo -ne '\015'`
    screen -S $SCREEN_NAME -X stuff 'fan p 3 min 25'`echo -ne '\015'`
    screen -S $SCREEN_NAME -X stuff 'fan p 4 min 25'`echo -ne '\015'`
    screen -S $SCREEN_NAME -X stuff 'fan p 5 min 25'`echo -ne '\015'`
    screen -S $SCREEN_NAME -X stuff 'fan p 6 min 25'`echo -ne '\015'`
    screen -S $SCREEN_NAME -X stuff 'fan p 7 min 25'`echo -ne '\015'`

    # This is from jazinheira's script, I left it here as an example
    # However I doubt it has any effect since we are using freeipmi to get the temperatures.
    #
    # Ignore HD sensors due to non-HP branded HDDs.
    #screen -S $SCREEN_NAME -X stuff 'fan t 3 off'`echo -ne '\015'`
    #screen -S $SCREEN_NAME -X stuff 'fan t 19 off'`echo -ne '\015'`
    #screen -S $SCREEN_NAME -X stuff 'fan t 20 off'`echo -ne '\015'`
    #
    # Increase setpoint of PCIe sensors, otherwise fans will be minimum 30%.
    # 5500 sets a target of 55C after which the fans start ramping up.
    #screen -S $SCREEN_NAME -X stuff 'fan pid 23 sp 5500'`echo -ne '\015'`
    #screen -S $SCREEN_NAME -X stuff 'fan pid 25 sp 5500'`echo -ne '\015'`
    #screen -S $SCREEN_NAME -X stuff 'fan pid 26 sp 5500'`echo -ne '\015'`

else
    echo "Found screen session $SCREEN_NAME"
fi


while getopts "l" flag;
do
    case "$flag" in
        l) LOGARITHMIC=1;;
    esac
done

adjust_fan_speed() {
    local TEMPERATURE=$1
    local FAN_GROUP=$2
    local SPEED_LIN
    local SPEED_LOG
    local SPEED


    if [ "$TEMPERATURE" -le $MIN_TEMP ]; then
        SPEED=$((LOGARITHMIC = 1 ? MIN_SPEED_LOG : MIN_SPEED))
    elif [ "$TEMPERATURE" -ge $MAX_TEMP ]; then
        SPEED=$MAX_SPEED
    else
        # Calculate speed based on the temperature
        # Linear growth
        SPEED_LIN=$(($MIN_SPEED + ($TEMPERATURE - $MIN_TEMP) * $SPEED_RANGE / $TEMP_RANGE))
        # Logarithmic growth
        SPEED_LOG=$(echo "$MIN_SPEED_LOG * 1.092^($TEMPERATURE-$MIN_TEMP_LOG)" | bc -l)
        SPEED_LOG=${SPEED_LOG%.*}
        # Is logarithmic curve option ON ?
        SPEED=$((LOGARITHMIC == 1 ? SPEED_LOG : SPEED_LIN))
    fi

    # Apply the calculated speed to each fan in the group
    for FAN in $FAN_GROUP; do
        screen -S $SCREEN_NAME -X stuff "fan p $FAN max $SPEED"`echo -ne '\015'`
    done
    SPEED_PERCENT=$(printf "%.2f\n" $(echo "($SPEED/$MAX_SPEED)*100" | bc -l))
    echo -e "\033[1;34mApplied speed $SPEED PWM ($SPEED_PERCENT%)\033[0m"
}

# Read temperatures from sensors and IPMI
CPU1_TEMP=$(sensors -Aj coretemp-isa-0000 | jq '.[][] | to_entries[] | select(.key | endswith("input")) | .value' | sort -rn | head -n1)
#CPU2_TEMP=$(sensors -Aj coretemp-isa-0001 | jq '.[][] | to_entries[] | select(.key | endswith("input")) | .value' | sort -rn | head -n1)
HIGHEST_TEMP_IPMI=$(ipmi-sensors -t Temperature --exclude-record-ids=$HD_ID --ignore-not-available-sensors --comma-separated-output --sdr-cache-recreate | awk -F, 'NR>1 && $4+0 == $4 {if ($4 > max) {max = $4}} END {print int(max)}')
HD_TEMP=$(ipmi-sensors -t Temperature -s $HD_ID --ignore-not-available-sensors --comma-separated-output --sdr-cache-recreate | awk -F, 'NR>1 && $4+0 == $4 {if ($4 > max) {max = $4}} END {print int(max)}')

# Convert temperatures to integers and find the highest
CPU1_TEMP=${CPU1_TEMP%.*}
CPU2_TEMP=${CPU2_TEMP%.*}
HIGHEST_TEMP_IPMI=${HIGHEST_TEMP_IPMI%.*}
HD_TEMP=${HD_TEMP%.*}
HIGHEST_TEMP=$((CPU1_TEMP > CPU2_TEMP ? CPU1_TEMP : CPU2_TEMP))
HIGHEST_TEMP=$((HIGHEST_TEMP > HIGHEST_TEMP_IPMI ? HIGHEST_TEMP : HIGHEST_TEMP_IPMI))
HIGHEST_TEMP=$((HD_TEMP > HD_MAX ? HD_TEMP : HIGHEST_TEMP))

# Prepare for output (
SPEED_LOG_OUT=$(echo "$MIN_SPEED_LOG * 1.092^($HIGHEST_TEMP-$MIN_TEMP_LOG)" | bc )
SPEED_LOG_OUT=${SPEED_LOG_OUT%.*}
SPEED_LIN_OUT=$(($MIN_SPEED + ($HIGHEST_TEMP - $MIN_TEMP) * $SPEED_RANGE / $TEMP_RANGE))

# Output info
echo "Temperatures:"
echo "CPU1: $CPU1_TEMP°C"
#echo "CPU2: $CPU2_TEMP°C"
echo "CPU2: offline"
echo "HD Controller: $HD_TEMP°C"
echo "Highest IPMI: $HIGHEST_TEMP_IPMI°C"
echo "Highest: $HIGHEST_TEMP°C"
echo "Linear fan speed : $SPEED_LIN_OUT"
echo "Logarithmic fan speed : $SPEED_LOG_OUT"

# Adjust fan speeds based on the highest temperature
adjust_fan_speed "$HIGHEST_TEMP" "$FAN_GROUP"

echo -e "Sleeping 30 seconds..."
sleep 30
done

else
        PID=$(pgrep -x fanctrl)
        echo "fanctrl is already running on PID $PID"
fi
