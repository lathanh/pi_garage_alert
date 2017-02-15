Pi Garage Alert
===============

Raspberry Pi Python script to email, tweet, or send an SMS if a garage door is
left open.

![Screenshot of garage door SMS alert](http://www.richlynch.com/wp-content/uploads/2013/07/garage_door_sms.png)

Quick Start
---------------
Here is a heavily condensed quick start guide.
New users are strongly encouraged to read the full documentation at
http://www.richlynch.com/code/pi_garage_alert.

1. Equipment required
   1. Raspberry Pi model A or B
   2. 2GB or larger SD card for the RPi filesystem
   3. Magnetic sensor (e.g. http://www.smarthome.com/7455/Seco-Larm-SM-226L-Garage-Door-Contacts-for-Closed-Circuits/p.aspx)
   4. USB wifi adapter (if not using Ethernet)
   5. USB power supply for RPi
2. Connect one wire of the magnetic sensor to a GPIO pin on the RPi and the
   other to a ground pin on the RPi. It is a good idea to put a 1kohm resistor
   in series with the sensor to protect the RPi from damage if anything is
   misconfigured.
3. Raspberry Pi initial setup
   1. Follow the guide at http://elinux.org/RPi_Easy_SD_Card_Setup to write the
      Raspbian image to the SD card.
   2. Boot the RPi and at raspi-config, expand the filesystem, set the "pi"
      account password, set the hostname, and enable SSH.
   3. Reboot the Raspberry Pi
4. Edit `/etc/wpa_supplicant/wpa_supplicant.conf` and configure the RPi to
   connect to your wifi network.
5. Regenerate the ssh keys for security.
6. Update the packages with `sudo apt-get update && sudo apt-get upgrade`, then
   install the dependencies:

        sudo apt-get install python-setuptools python-dev libffi-dev
        sudo easy_install pip
        sudo pip install sleekxmpp
        sudo pip install tweepy
        sudo pip install twilio
        sudo pip install requests
        sudo pip install requests[security]

7. Optional email configuration
   1. Configure postfix to send mail using Google SMTP, or your ISP's SMTP
      server
8. Optional twitter configuration
   2. On https://dev.twitter.com/apps/new, create a new application
9. Optional twillio (SMS) configuration
   3. Sign up for a Twilio account at http://www.twilio.com.
10. Copy `bin/pi_garage_alert.py` to `/usr/local/sbin`
11. Copy `etc/pi_garage_alert_config.py` to `/usr/local/etc`.
    Edit this file and specify the garage doors you have and alerts you'd like.
12. Copy `init.d/pi_garage_alert` to `/etc/init.d`
13. Configure and start the service with

        sudo update-rc.d pi_garage_alert defaults
        sudo service pi_garage_alert start

14. At this point, the Pi Garage Alert software should be running. You can view
    its log in `/var/log/pi_garage_alert.log`

Other Uses
---------------
The script will work with any sensor that can act like a switch. Some alternate uses include:

* Basement or washing machine leak sensors
* Window sensors
