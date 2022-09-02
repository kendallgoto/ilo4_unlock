# ilo4_unlock (Silence of the Fans)
A toolkit for patching HPE's iLO 4 firmware with access to previously inaccessible utilities.

Specifically, firmware is patched with the ability to access new commands via SSH, relating to system health (`h`), fan tuning (`fan`), on-board temperature sensors (`ocsd`), and option chip health systems (`ocbb`). Designed for [/r/homelab](https://reddit.com/r/homelab) users, this modified firmware provides administrators with the ability to adjust HP's aggressive fan curves on iLO4-equipped servers (such as DL380p / DL380p Gen 8 & Gen 9). Another common use case is to prevent server fans from maxing out when a non-HPE certified PCI-e card is used in a system.

**Please note: At this time, v2.77 is the most recent iLO that has a working patch. After this version, HP has removed many of the control utilities that make patching v2.78 and v2.79 useful. While this may change in the future, bringing useful tools to v2.79 (the current latest) will take an extremely large amount of work. The patching works fine here, it just does not provide access to useful functions**

## Legal
There is risk for potential damage to your system when utilizing this code. If an error occurs during flashing, or you end up flashing corrupted firmware, the iLO will not be able to recover itself. The iLO's flash chip cannot be programmed on-board, and must be fully desoldered and reprogrammed to recover the functionality. Additionally, utilizing the included new features may cause your server to overheat or otherwise suffer damage. Do not proceed with installing this firmware if you don't know what you're doing. **You have been warned**. There is no warranty for this code nor will I be responsible for any damage you cause. I have personally only tested this firmware on my DL380p Gen8, and DL380e Gen8.

This repo does not contain any iLO 4 binaries; unmodified or patched as they are owned by HP. Websites have, in the past, been served with cease and desist orders from HP for hosting iLO binaries. For security purposes, I encourage you to follow the steps listed to build the patched version of the iLO yourself, while verifying the contents of the patched code.

## Getting Started
Python 2.7 is required. I built everything on CentOS 8; Other OS/environments might have different requirements. If your setup takes extra effort, please let me know and I'll document it.

_pro tip! if you're doing this all on a Live CD to flash, make sure you disable iLO security first, or you'll have to restart. See Flashing Firmware for more info_

Here is my setup for my Ubuntu 21.10 Live CD:
```bash
sudo apt-add-repository universe
sudo apt update
sudo apt-get install python2-minimal git curl
curl https://bootstrap.pypa.io/pip/2.7/get-pip.py --output get-pip.py && sudo python2 get-pip.py
python2 -m pip install virtualenv
git clone --recurse-submodules https://github.com/kendallgoto/ilo4_unlock.git
cd ilo4_unlock
python2 -m virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Building Firmware
``` bash
./build.sh init # download necessary HPE binaries
#./build.sh [patch-name] -- see patches/ folder for more info on each patch!
./build.sh 277  # generate iLO v2.77 patched firmware
# The build setup creates a build/ folder where all the artifacts are stored. The final firmware location will be printed at the end of the script, if no errors are produced.
```
## Flashing Firmware
The resulting firmware is located in the `build` directory, under the firmware's name (e.g. `build/ilo4_273.bin.patched` for v2.73 builds). I suggest the following steps to flash the firmware, as you cannot do it from the web interface:
1. Copy the resulting firmware to a USB key, along with the flasher files (`binaries/flash_ilo4` & `binaries/CP027911.xml`)
2. Remove power from your server, and enable iLO4 Security Override (for me, this was flipping the first DIP switch on the board).
3. Boot your server from a baremetal Linux install -- a Ubuntu LiveCD works well.
4. Ensure any HP modules are unloaded (`sudo modprobe -r hpilo`)
5. Plug in the USB key, rename the firmware to `ilo4_250.bin`, then run `sudo ./flash_ilo4 --direct` to patch your server.
6. Resist the urge to unplug the system and break everything while flashing. **It will be loud**. It took 2 minutes to erase, and 1 minute to flash.
7. After patching, shut down and remove power from the server to disable the iLO4 security override.

Following the Getting Started steps, here's what I did after building:
```bash
sudo modprobe -r hpilo
mkdir -p flash
cp binaries/flash_ilo4 binaries/CP027911.xml flash/
cp build/ilo4_277.bin.patched flash/ilo4_250.bin
cd flash
sudo ./flash_ilo4 --direct
# wait until the fans spin down ...
sudo shutdown now # remove power and disable the security override after shutting down!
```

## Use
```
FAN:
Usage:

  info [t|h|a|g|p]
                - display information about the fan controller
                  or individual information.
  g             - configure the 'global' section of the fan controller
  g smsc|start|stop|status
          start - start the iLO fan controller
          stop - stop the iLO fan controller
          smsc - configure the SMSC for manual control
       ro|rw|nc - set the RO, RW, NC (no_commit) options
    (blank)     - shows current status
  t             - configure the 'temperature' section of the fan controller
  t N on|off|adj|hyst|caut|crit|access|opts|set|unset
             on - enable temperature sensor
            off - disable temperature sensor
            adj - set ADJUSTMENT/OFFSET
      set/unset - set or clear a fixed simulated temp (also 'fan t set/unset' for show/clear all)
           hyst - set hysteresis for sensor
           caut - set CAUTION threshold
           crit - set CRITICAL threshold
         access - set ACCESS method for sensor (should be followed by 5 BYTES)
           opts - set the OPTION field
  h             - configure the 'tacHometers' section of the fan controller
  h N on|off|min|hyst|access
             on - enable sensor N
            off - disable sensor N
            min - set MINIMUM tach threshold
           hyst - set hysteresis
 grp ocsd|show  - show grouping parameters with OCSD impacts
  p             - configure the PWM configuration
  p N on|off|min|max|hyst|blow|pctramp|zero|feton|bon|boff|status|lock X|unlock|tickler|fix|fet|access
             on - enable (toggle) specified PWM
            off - disable (toggle) specified PWM
            min - set MINIMUM speed
            max - set MAXIMUM speed
           blow - set BLOWOUT speed
            pct - set the PERCETNAGE blowout bits
           ramp - set the RAMP register
           zero - set the force ZEROP bit on/off
          feton - set the FET 'for off' bit on/off
            bon - set BLOWOUT on
           boff - set BLOWOUT off
         status - set STATUS register
           lock - set LOCK speed and set LOCK bit
         unlock - clear the LOCK bit
        tickler - set TICKLER bit on/off - tickles fans even if FAN is stopped
  pid           - configure the PID algorithm
  pid N p|i|d|sp|imin|imax|lo|hi  - configure PID paramaters
                                  - * Use correct FORMAT for numbers!
             p - set the PROPORTIONAL gain
             i - set the INTEGRAL gain
             d - set the DERIVATIVE gain
            sp - set SETPOINT
          imin - set I windup MIN value
          imax - set I windup MAX value
            lo - set output LOW limit
            hi - set output HIGH lmit
 MISC
  rate X        - Change rate to X ms polling (default 3000)
  ramp          - Force a RAMP condition
  dump          - Dump all the fan registers in raw HEX format
  hyst h v1..vN - Perform a test hysteresis with supplied numbers
  desc <0>..<15> - try to decode then execute raw descriptor bytes (5 or 16)
  actn <0>..<15> - try to decode then execute raw action bytes (5 or 16)
  debug trace|t X|h X|a X|g X|p X|off|on
                - Set the fine control values for the fan FYI level
  DIMM          - DIMM-specific subcommand handler
  DRIVE         - Drive temperature subcommand handler
  MB            - Memory buffer subcommand handler
  PECI          - PECI subcommand handler
 AWAITING DOCUMENTAION
  ms  - multi-segment info
  a N  - algorithms - set parameters for multi-segment.
  w   - weighting
```
See the [scripts/](scripts/) folder as well.
For info about the lesser used functions, please refer to the relevant reading. I don't use them, so I haven't documented them.

## Getting Involved
Want to get involved? Check out [here](CONTRIBUTING.md)!

## Credits
- Thanks to the work of [Airbus Security Lab](https://github.com/airbus-seclab/ilo4_toolbox); whose previous work exploring iLO 4 & 5 was instrumental in allowing the development of modified iLO firmware.
- And to [/u/phoenixdev](https://www.reddit.com/user/phoenixdev), whose original work on iLO4 v2.60 and v2.73 allowed for fans to be controlled in the first place.  
This repository utilizes modified code from the iLO4 Toolbox. The toolkit invokes code directly from the iLO4 Toolbox, as well as includes modified versions of Airbus Security Lab's original patching code to perform the necessary patches. It also utilizes code originally written by [/u/phoenixdev](https://www.reddit.com/user/phoenixdev) that was reverse-engineered from their patched v2.73 iLO4 firmware.

The full documentation on how this code base was derived is fully detailed [in the research/ folder](research/readme.md).

## Relevant Reading & Prior Work
[2019-10-02 /u/phoenixdev's preliminary writeup](https://www.reddit.com/r/homelab/comments/dc7dbc/silence_of_the_fans_preliminary_success_with/)  
[2019-10-15 /u/phoenixdev's first release for v2.60](https://www.reddit.com/r/homelab/comments/di3vrk/silence_of_the_fans_controlling_hp_server_fans/)  
[2020-06-30 /u/phoenixdev's second release for v2.73](https://www.reddit.com/r/homelab/comments/di3vrk/silence_of_the_fans_controlling_hp_server_fans/)  
[Airbus Security Lab's iLO4 Toolbox](https://github.com/airbus-seclab/ilo4_toolbox)  
[Airbus Security Lab's "Subverting your server through its BMC: the HPE iLO4 case" (written version)](https://airbus-seclab.github.io/ilo/SSTIC2018-Article-subverting_your_server_through_its_bmc_the_hpe_ilo4_case-gazet_perigaud_czarny.pdf)  
[Airbus Security Lab's "Subverting your server through its BMC: the HPE iLO4 case" (presented version)](https://airbus-seclab.github.io/ilo/RECONBRX2018-Slides-Subverting_your_server_through_its_BMC_the_HPE_iLO4_case-perigaud-gazet-czarny.pdf)  
