#!/usr/bin/env bash
#
# Modified from aterfax-silence-dl380pG8-screen.sh by https://github.com/Aterfax in PR #3
#
# Set up using Cron rules (crontab -e)
# @reboot /home/whatever/my-start-script.sh # trigger script at bootup
# */6 * * * * /usr/bin/screen -S iLO4fansession -X stuff 'fan info'`echo -ne '\015'` # send fan info regularly to keep alive
#
# This setup is tuned for my DL20 Gen 9 server with additional PCIe cards.
# You should monitor your temps and your workload, but fans should still ramp up since this doesn't disable most sensors.
#
# We establish a screen session, SSH to iLO4 and "stuff" it with commands.
# This preserves the first TTY in the screen session connected with iLO4
# so further command input/output can be visualised.
# We're avoiding the "output only goes in the first SSH session/TTY" bug!
#
# SSH is using SSH keys to connect in this example. Generate a key then add in iLO.

IP=X.X.X.X # CHANGEME
SCREEN_NAME=iLO4fansession
SSH_USER=Administrator # You should set up a different user in iLO, no extra permissions are needed for the user.
SSH_KEY=~/.ssh/foo # Set to the location of the SSH key for the above user.

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

screen -S $SCREEN_NAME -X stuff "ssh -i ${SSH_KEY} -t  ${SSH_USER}@${IP} -p 2222 -o PubKeyAcceptedKeyTypes=+ssh-rsa -o HostKeyAlgorithms=+ssh-dss -o KexAlgorithms=+diffie-hellman-group14-sha1 -o LocalCommand='fan info'"`echo -ne '\015'`

echo -e "Sleeping for 5 seconds."

sleep 5

echo -e "Resuming fan commands."

# `echo -ne '\015'` emulates pressing the Enter key.

# Set fan minimums.
screen -S $SCREEN_NAME -X stuff 'fan p 0 min 25'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan p 1 min 25'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan p 2 min 25'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan p 3 min 25'`echo -ne '\015'`


# Ignore HD sensors due to non-HP branded HDDs.
screen -S $SCREEN_NAME -X stuff 'fan t 3 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 19 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 20 off'`echo -ne '\015'`

# Increase setpoint of PCIe sensors, otherwise fans will be minimum 30%.
# 5500 sets a target of 55C after which the fans start ramping up.
screen -S $SCREEN_NAME -X stuff 'fan pid 23 sp 5500'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan pid 25 sp 5500'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan pid 26 sp 5500'`echo -ne '\015'`
