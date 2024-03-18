#!/bin/bash

###
### This script adjusts the fan speed based on the highest temperature
### Use with https://github.com/kendallgoto/ilo4_unlock/blob/main/scripts/ja-silence-dl20G9.sh to unlock the iLO4 fan control and run the original script first to establish a screen session.
### Then this script can run via a .timer unit to adjust the fan speed every x seconds/minutes.
###
### Required packages: freeipmi, lm-sensors, jq, screen
### freeipmi might need additional configuration if the os you're executing this on isn't the same as the server you're trying to control.
### You can also use ipmitool instead of freeipmi, but you'll need to adjust the script accordingly. I had issues with ipmitool correctly formatting how I wanted things, ipmi-sensors was much easier to work with.
###
### Example .timer unit:
### [Unit]
### Description=Adjust fan speed
###
### [Timer]
### OnBootSec=10s
### OnUnitActiveSec=1m
### Unit=fan_autocontrol.service
###
### [Install]
### WantedBy=timers.target  
###
### Example .service unit:
### [Unit]
### Description=Adjust fan speed
###
### [Service]
### Type=oneshot
### ExecStart=/path/to/fan_autocontrol.sh (name of this script)
###
### [Install]
### WantedBy=multi-user.target
###


# Configuration
SCREEN_NAME="iLO4fansession"
MIN_TEMP=45  # Lowered the minimum temperature to 45 degrees Celsius
MAX_TEMP=67
MIN_SPEED=40
MAX_SPEED=255
TEMP_RANGE=$((MAX_TEMP - MIN_TEMP))  # 22
SPEED_RANGE=$((MAX_SPEED - MIN_SPEED))  # 215

adjust_fan_speed() {
    local TEMPERATURE=$1
    local FAN_GROUP=$2
    local SPEED

    if [ "$TEMPERATURE" -le $MIN_TEMP ]; then
        SPEED=$MIN_SPEED
    elif [ "$TEMPERATURE" -ge $MAX_TEMP ]; then
        SPEED=$MAX_SPEED
    else
        # Calculate speed based on the temperature
        SPEED=$(($MIN_SPEED + ($TEMPERATURE - $MIN_TEMP) * $SPEED_RANGE / $TEMP_RANGE))
    fi

    # Apply the calculated speed to each fan in the group
    for FAN in $FAN_GROUP; do
        screen -S $SCREEN_NAME -X stuff "fan p $FAN max $SPEED"`echo -ne '\015'`
    done
}

# Read temperatures from sensors and IPMI
CPU1_TEMP=$(sensors -Aj coretemp-isa-0000 | jq '.[][] | to_entries[] | select(.key | endswith("input")) | .value' | sort -rn | head -n1)
CPU2_TEMP=$(sensors -Aj coretemp-isa-0001 | jq '.[][] | to_entries[] | select(.key | endswith("input")) | .value' | sort -rn | head -n1)
HIGHEST_TEMP_IPMI=$(ipmi-sensors -t Temperature --ignore-not-available-sensors --comma-separated-output | awk -F, 'NR>1 && $4+0 == $4 {if ($4 > max) {max = $4}} END {print int(max)}')

# Convert temperatures to integers and find the highest
CPU1_TEMP=${CPU1_TEMP%.*}
CPU2_TEMP=${CPU2_TEMP%.*}
HIGHEST_TEMP_IPMI=${HIGHEST_TEMP_IPMI%.*}
HIGHEST_TEMP=$((CPU1_TEMP > CPU2_TEMP ? CPU1_TEMP : CPU2_TEMP))
HIGHEST_TEMP=$((HIGHEST_TEMP > HIGHEST_TEMP_IPMI ? HIGHEST_TEMP : HIGHEST_TEMP_IPMI))

# Output the highest temperature
echo "Temperatures:"
echo "CPU1: $CPU1_TEMP°C"
echo "CPU2: $CPU2_TEMP°C"
echo "Highest IPMI: $HIGHEST_TEMP_IPMI°C"
echo "Highest: $HIGHEST_TEMP°C"

# Define fan groups based on your setup
FAN_GROUP="0 1 2 3 4 5"  # Example fan group

# Adjust fan speeds based on the highest temperature
adjust_fan_speed "$HIGHEST_TEMP" "$FAN_GROUP"
