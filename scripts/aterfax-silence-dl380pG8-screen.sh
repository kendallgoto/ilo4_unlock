#!/usr/bin/env bash
#
# Provided by https://github.com/Aterfax in PR #3
# Set up using Cron rules (crontab -e)
# @restart /home/whatever/my-start-script.sh # trigger script at bootup
# */6 * * * * /usr/bin/screen -S my-screen-name -X stuff 'fan info'`echo -ne '\015'` # send fan info regularly to keep alive
#
# This setup is tuned for my DL380p Gen8 LFF server with additional PCIe cards.
# We establish a screen session, SSH to iLO4 and "stuff" it with commands.
# This preserves the first TTY in the screen session connected with iLO4
# so further command input/output can be visualised.
# We're avoiding the "output only goes in the first SSH session/TTY" bug!
#
# SSH is reliant on you using SSH keys and having these setup already.

IP=X.X.X.X # CHANGEME
SCREEN_NAME=iLO4fansession

IP=${IP} screen -dmS $SCREEN_NAME

echo -e "Establishing SSH session inside screen."

screen -S $SCREEN_NAME -X stuff 'ssh -t  Administrator@${IP} -o LocalCommand="fan info"'`echo -ne '\015'`

echo -e "Sleeping for 5 seconds."

sleep 5

echo -e "Resuming fan commands."

# `echo -ne '\015'` emulates pressing the Enter key.

# Set fan minimums.
screen -S $SCREEN_NAME -X stuff 'fan p 0 min 50'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan p 1 min 50'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan p 2 min 50'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan p 3 min 65'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan p 4 min 65'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan p 5 min 65'`echo -ne '\015'`

# Ignore HD Cage sensor due to non-HP branded HDDs.
screen -S $SCREEN_NAME -X stuff 'fan t 12 off'`echo -ne '\015'`

# Ignore PCIe slots cage 1 sensors?
screen -S $SCREEN_NAME -X stuff 'fan t 32 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 33 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 34 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 35 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 36 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 37 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 38 off'`echo -ne '\015'`

# Ignore PCIe slots cage 2 sensors?
screen -S $SCREEN_NAME -X stuff 'fan t 52 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 53 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 54 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 55 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 56 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 57 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 58 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 59 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 60 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 61 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 62 off'`echo -ne '\015'`
screen -S $SCREEN_NAME -X stuff 'fan t 63 off'`echo -ne '\015'`

