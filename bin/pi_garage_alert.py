#!/usr/bin/python2.7
""" Pi Garage Alert

Original Author: Richard L. Lynch <rich@richlynch.com>
Modifications by: Robert LaThanh

Description: Emails, tweets, or sends an SMS if a garage door is left open
too long.

Learn more at http://www.richlynch.com/code/pi_garage_alert
"""

##############################################################################
#
# The MIT License (MIT)
#
# Copyright (c) 2013-2014 Richard L. Lynch <rich@richlynch.com>
# Copyright (c) 2017 Robert LaThanh
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
#
##############################################################################

import time
from time import strftime
import subprocess
import re
import sys
import json
import logging
from datetime import timedelta
import smtplib
import ssl
import traceback
from email.mime.text import MIMEText

import requests
import tweepy
import RPi.GPIO as GPIO
import httplib2
import sleekxmpp
from sleekxmpp.xmlstream import resolver, cert
from twilio.rest import TwilioRestClient
from twilio.rest.exceptions import TwilioRestException

sys.path.append('/usr/local/etc')
import pi_garage_alert_config as cfg

##############################################################################
# Cisco Spark support
##############################################################################
class CiscoSpark(object):
    """Class to send Cisco Spark messages"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.header = None
        self.rooms = {"items": []}
        self.room_id = None

    def headers(self):
        access_token_hdr = 'Bearer ' + cfg.SPARK_ACCESSTOKEN
        spark_header = {'Authorization': access_token_hdr, 'Content-Type': 'application/json; charset=utf-8'}
        return spark_header

    def get_rooms(self):
        uri = 'https://api.ciscospark.com/v1/rooms'
        resp = requests.get(uri, headers=self.headers)
        return resp.json()

    def find_room(self, name):
        room_id = 0
        for room in self.rooms["items"]:
            if room["title"] == name:
                room_id = room["id"]
                break
        return room_id

    def add_room(self, name):
        uri = 'https://api.ciscospark.com/v1/rooms'
        payload = {"title": name}
        resp = requests.post(uri, data=json.dumps(payload), headers=self.headers)
        return resp.json()

    def add_message_to_room(self, message):
        self.logger.info("In the Spark addMessageToRoom function. Adding to room ID " + self.room_id)
        uri = "https://api.ciscospark.com/v1/messages"
        payload = {"roomId": self.room_id, "text": message}
        resp = requests.post(uri, data=json.dumps(payload), headers=self.headers)
        return resp.json()

    def send_sparkmsg(self, room_name, message):
        """Sends a note to the specified Spark Room

        Args:
            roomName: Name of the Cisco Spark Room to send to.
            message: body of the message
        """
        self.logger.info("Sending Cisco Spark message to %s: message = \"%s\"", room_name, message)

        if cfg.SPARK_ACCESSTOKEN == '':
            self.logger.error("Cisco Spark access token not specified - unable to send Spark message!")

        self.logger.info("In the Spark block")
        self.header = self.headers()
        self.rooms = self.get_rooms()
        self.room_id = self.find_room(room_name)
        if self.room_id != 0:
            self.add_message_to_room(message)
        else:
            self.logger.info("Specified room %s was not found! Creating.", room_name)
            self.add_room(room_name)
            self.rooms = self.get_rooms()
            self.room_id = self.find_room(room_name)
            self.add_message_to_room(message)

##############################################################################
# Jabber support
##############################################################################

# SleekXMPP requires UTF-8
if sys.version_info < (3, 0):
    # pylint: disable=no-member
    reload(sys)
    sys.setdefaultencoding('utf8')

class Jabber(sleekxmpp.ClientXMPP):
    """Interfaces with a Jabber instant messaging service"""

    def __init__(self, doors):
        self.logger = logging.getLogger(__name__)
        self.connected = False

        # Keep references to doors list for status queries
        self.doors = doors

        if not hasattr(cfg, 'JABBER_ID'):
            self.logger.debug("Jabber ID not defined - Jabber support disabled")
            return
        if cfg.JABBER_ID == '':
            self.logger.debug("Jabber ID not configured - Jabber support disabled")
            return

        self.logger.info("Signing into Jabber as %s", cfg.JABBER_ID)

        sleekxmpp.ClientXMPP.__init__(self, cfg.JABBER_ID, cfg.JABBER_PASSWORD)

        # Register event handlers
        self.add_event_handler("session_start", self.handle_session_start)
        self.add_event_handler("message", self.handle_message)
        self.add_event_handler("ssl_invalid_cert", self.ssl_invalid_cert)

        # ctrl-c processing
        self.use_signals()

        # Setup plugins. Order does not matter.
        self.register_plugin('xep_0030') # Service Discovery
        self.register_plugin('xep_0004') # Data Forms
        self.register_plugin('xep_0060') # PubSub
        self.register_plugin('xep_0199') # XMPP Ping

        # If you are working with an OpenFire server, you may need
        # to adjust the SSL version used:
        # self.ssl_version = ssl.PROTOCOL_SSLv3

        # Connect to the XMPP server and start processing XMPP stanzas.
        # This will block if the network is down.

        if hasattr(cfg, 'JABBER_SERVER') and hasattr(cfg, 'JABBER_PORT'):
            # Config file overrode the default server and port
            if not self.connect((cfg.JABBER_SERVER, cfg.JABBER_PORT)): # pylint: disable=no-member
                return
        else:
            # Use default server and port from DNS SRV records
            if not self.connect():
                return

        # Start up Jabber threads and return
        self.process(block=False)
        self.connected = True

    def ssl_invalid_cert(self, raw_cert):
        """Handle an invalid certificate from the Jabber server
           This may happen if the domain is using Google Apps
           for their XMPP server and the XMPP server."""
        hosts = resolver.get_SRV(self.boundjid.server, 5222,
                                 'xmpp-client',
                                 resolver=resolver.default_resolver())

        domain_uses_google = False
        for host, _ in hosts:
            if host.lower()[-10:] == 'google.com':
                domain_uses_google = True

        if domain_uses_google:
            try:
                if cert.verify('talk.google.com', ssl.PEM_cert_to_DER_cert(raw_cert)):
                    logging.debug('Google certificate found for %s', self.boundjid.server)
                    return
            except cert.CertificateError:
                pass

        logging.error("Invalid certificate received for %s", self.boundjid.server)
        self.disconnect()

    def handle_session_start(self, event):
        """Process the session_start event.

        Typical actions for the session_start event are
        requesting the roster and broadcasting an initial
        presence stanza.

        Args:
            event: An empty dictionary. The session_start
                   event does not provide any additional
                   data.
        """
        # pylint: disable=unused-argument
        self.send_presence()
        self.get_roster()

    def handle_message(self, msg):
        """Process incoming message stanzas.

        Args:
            msg: Received message stanza
        """
        self.logger.info("Jabber from %s (%s): %s", msg['from'].bare, msg['type'], msg['body'])

        # Only handle one-to-one conversations, and only if authorized
        # users have been defined
        if msg['type'] in ('chat', 'normal') and hasattr(cfg, 'JABBER_AUTHORIZED_IDS'):
            # Check if user is authorized
            if msg['from'].bare in cfg.JABBER_AUTHORIZED_IDS:
                if msg['body'].lower() == 'status':
                    # Generate status report
                    states = []
                    for door in self.doors:
                        how_long = time.time() - door.time_of_last_state_change
                        states.append("%s: %s (%s)" % (door.name, door.state,
                                                       format_duration(how_long)))
                    response = ' / '.join(states)
                else:
                    # Invalid command received
                    response = "I don't understand that command. Valid commands are: status"
                self.logger.info("Replied to %s: %s", msg['from'], response)
                msg.reply(response).send()
            else:
                self.logger.info("Ignored unauthorized user: %s", msg['from'].bare)

    def send_msg(self, recipient, msg):
        """Send jabber message to specified recipient"""
        if not self.connected:
            self.logger.error("Unable to connect to Jabber - unable to send jabber message!")
            return

        self.logger.info("Sending Jabber message to %s: %s", recipient, msg)
        self.send_message(mto=recipient, mbody=msg)

    def terminate(self):
        """Terminate all jabber threads"""
        if self.connected:
            self.disconnect()

##############################################################################
# Twilio support
##############################################################################

class Twilio(object):
    """Class to connect to and send SMS using Twilio"""

    def __init__(self):
        self.twilio_client = None
        self.logger = logging.getLogger(__name__)

    def send_sms(self, recipient, msg):
        """Sends SMS message to specified phone number using Twilio.

        Args:
            recipient: Phone number to send SMS to.
            msg: Message to send. Long messages will automatically be truncated.
        """

        # User may not have configured twilio - don't initialize it until it's
        # first used
        if self.twilio_client is None:
            self.logger.info("Initializing Twilio")

            if cfg.TWILIO_ACCOUNT == '' or cfg.TWILIO_TOKEN == '':
                self.logger.error("Twilio account or token not specified - unable to send SMS!")
            else:
                self.twilio_client = TwilioRestClient(cfg.TWILIO_ACCOUNT, cfg.TWILIO_TOKEN)

        if self.twilio_client != None:
            self.logger.info("Sending SMS to %s: %s", recipient, msg)
            try:
                self.twilio_client.sms.messages.create(
                    to=recipient,
                    from_=cfg.TWILIO_PHONE_NUMBER,
                    body=truncate(msg, 140))
            except TwilioRestException as ex:
                self.logger.error("Unable to send SMS: %s", ex)
            except httplib2.ServerNotFoundError as ex:
                self.logger.error("Unable to send SMS - internet connectivity issues: %s", ex)
            except:
                self.logger.error("Exception sending SMS: %s", sys.exc_info()[0])

##############################################################################
# Twitter support
##############################################################################

class Twitter(object):
    """Class to connect to and send DMs/update status on Twitter"""

    def __init__(self):
        self.twitter_api = None
        self.logger = logging.getLogger(__name__)

    def connect(self):
        """Initialize Twitter API object.

        Args:
            None
        """

        # User may not have configured twitter - don't initialize it until it's
        # first used
        if self.twitter_api is None:
            self.logger.info("Initializing Twitter")

            if cfg.TWITTER_CONSUMER_KEY == '' or cfg.TWITTER_CONSUMER_SECRET == '':
                self.logger.error("Twitter consumer key/secret not specified - unable to Tweet!")
            elif cfg.TWITTER_ACCESS_KEY == '' or cfg.TWITTER_ACCESS_SECRET == '':
                self.logger.error("Twitter access key/secret not specified - unable to Tweet!")
            else:
                auth = tweepy.OAuthHandler(cfg.TWITTER_CONSUMER_KEY, cfg.TWITTER_CONSUMER_SECRET)
                auth.set_access_token(cfg.TWITTER_ACCESS_KEY, cfg.TWITTER_ACCESS_SECRET)
                self.twitter_api = tweepy.API(auth)

    def direct_msg(self, user, msg):
        """Send direct message to specified Twitter user.

        Args:
            user: User to send DM to.
            msg: Message to send. Long messages will automatically be truncated.
        """

        self.connect()

        if self.twitter_api != None:
            # Twitter doesn't like the same msg sent over and over, so add a timestamp
            msg = strftime("%Y-%m-%d %H:%M:%S: ") + msg

            self.logger.info("Sending twitter DM to %s: %s", user, msg)
            try:
                self.twitter_api.send_direct_message(user=user, text=truncate(msg, 140))
            except tweepy.error.TweepError as ex:
                self.logger.error("Unable to send Tweet: %s", ex)

    def update_status(self, msg):
        """Update the user's status

        Args:
            msg: New status to set. Long messages will automatically be truncated.
        """

        self.connect()

        if self.twitter_api != None:
            # Twitter doesn't like the same msg sent over and over, so add a timestamp
            msg = strftime("%Y-%m-%d %H:%M:%S: ") + msg

            self.logger.info("Updating Twitter status to: %s", msg)
            try:
                self.twitter_api.update_status(status=truncate(msg, 140))
            except tweepy.error.TweepError as ex:
                self.logger.error("Unable to update Twitter status: %s", ex)

##############################################################################
# Email support
##############################################################################

class Email(object):
    """Class to send emails"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def send_email(self, recipient, subject, msg):
        """Sends an email to the specified email address.

        Args:
            recipient: Email address to send to.
            subject: Email subject.
            msg: Body of email to send.
        """
        self.logger.info("Sending email to %s: subject = \"%s\", message = \"%s\"", recipient, subject, msg)

        msg = MIMEText(msg)
        msg['Subject'] = subject
        msg['To'] = recipient
        msg['From'] = cfg.EMAIL_FROM
        msg['X-Priority'] = cfg.EMAIL_PRIORITY

        try:
            mail = smtplib.SMTP(cfg.SMTP_SERVER, cfg.SMTP_PORT)
            mail.ehlo()
            if cfg.SMTP_IS_TLS:
                mail.starttls()
                mail.ehlo()
            if cfg.SMTP_USER != '' and cfg.SMTP_PASS != '':
                mail.login(cfg.SMTP_USER, cfg.SMTP_PASS)
            mail.sendmail(cfg.EMAIL_FROM, recipient, msg.as_string())
            mail.close()
        except:
            self.logger.error("Exception sending email: %s", sys.exc_info()[0])

##############################################################################
# Pushbullet support
##############################################################################

class Pushbullet(object):
    """Class to send Pushbullet notes"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def send_note(self, access_token, title, body):
        """Sends a note to the specified access token.

        Args:
            access_token: Access token of the Pushbullet account to send to.
            title: Note title
            body: Body of the note to send
        """
        self.logger.info("Sending Pushbullet note to %s: title = \"%s\", body = \"%s\"", access_token, title, body)

        headers = {'Content-type': 'application/json'}
        payload = {'type': 'note', 'title': title, 'body': body}

        try:
            session = requests.Session()
            session.auth = (access_token, "")
            session.headers.update(headers)
            session.post("https://api.pushbullet.com/v2/pushes", data=json.dumps(payload))
        except:
            self.logger.error("Exception sending note: %s", sys.exc_info()[0])

##############################################################################
# IFTTT support using Maker Channel (https://ifttt.com/maker)
##############################################################################

class IFTTT(object):
    """Class to send IFTTT triggers using the Maker Channel"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def send_trigger(self, event, value1, value2, value3):
        """Send an IFTTT event using the maker channel.

        Get the key by following the URL at https://ifttt.com/services/maker/settings

        Args:
            event: Event name
            value1, value2, value3: Optional data to supply to IFTTT.
        """
        self.logger.info("Sending IFTTT event \"%s\": value1 = \"%s\", value2 = \"%s\", value3 = \"%s\"", event, value1, value2, value3)

        headers = {'Content-type': 'application/json'}
        payload = {'value1': value1, 'value2': value2, 'value3': value3}
        try:
            requests.post("https://maker.ifttt.com/trigger/%s/with/key/%s" % (event, cfg.IFTTT_KEY), headers=headers, data=json.dumps(payload))
        except:
            self.logger.error("Exception sending IFTTT event: %s", sys.exc_info()[0])

##############################################################################
# Google Cloud Messaging support
##############################################################################

class GoogleCloudMessaging(object):
    """Class to send GCM notifications"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def send_push(self, state, body):
        """Sends a push notification to the specified topic.

        Args:
            state: Garage door state as string ("0"|"1")
            body: Body of the note to send
        """
        status = "1" if state == 'open' else "0"

        self.logger.info("Sending GCM push to %s: status = \"%s\", body = \"%s\"", cfg.GCM_TOPIC, status, body)

        auth_header = "key=" + cfg.GCM_KEY
        headers = {'Content-type': 'application/json', 'Authorization': auth_header}
        payload = {'to': cfg.GCM_TOPIC, 'data': {'message': body, 'status': status}}

        try:
            session = requests.Session()
            session.headers.update(headers)
            session.post("https://gcm-http.googleapis.com/gcm/send", data=json.dumps(payload))
        except:
            self.logger.error("Exception sending push: %s", sys.exc_info()[0])

##############################################################################
# Sensor support
##############################################################################

def get_garage_door_state(pin):
    """Returns the state of the garage door on the specified pin as a string

    Args:
        pin: GPIO pin number.
    """
    if GPIO.input(pin): # pylint: disable=no-member
        state = 'open'
    else:
        state = 'closed'

    return state

def get_uptime():
    """Returns the uptime of the RPi as a string
    """
    with open('/proc/uptime', 'r') as uptime_file:
        uptime_seconds = int(float(uptime_file.readline().split()[0]))
        uptime_string = str(timedelta(seconds=uptime_seconds))
    return uptime_string

def get_gpu_temp():
    """Return the GPU temperature as a Celsius float
    """
    cmd = ['vcgencmd', 'measure_temp']

    measure_temp_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    output = measure_temp_proc.communicate()[0]

    gpu_temp = 'unknown'
    gpu_search = re.search('([0-9.]+)', output)

    if gpu_search:
        gpu_temp = gpu_search.group(1)

    return float(gpu_temp)

def get_cpu_temp():
    """Return the CPU temperature as a Celsius float
    """
    cpu_temp = 'unknown'
    with open("/sys/class/thermal/thermal_zone0/temp", "r") as temp_file:
        cpu_temp = float(temp_file.read()) / 1000.0

    return cpu_temp

def rpi_status():
    """Return string summarizing RPi status
    """
    return "CPU temp: %.1f, GPU temp: %.1f, Uptime: %s" % (get_gpu_temp(), get_cpu_temp(), get_uptime())

##############################################################################
# Logging and alerts
##############################################################################

def send_alerts(logger, alert_senders, recipients, subject, msg, state, time_in_state):
    """Send subject and msg to specified recipients

    Args:
        recipients: An array of strings of the form type:address
        subject: Subject of the alert
        msg: Body of the alert
        state: The state of the door
    """
    for recipient in recipients:
        if recipient[:6] == 'email:':
            alert_senders['Email'].send_email(recipient[6:], subject, msg)
        elif recipient[:11] == 'twitter_dm:':
            alert_senders['Twitter'].direct_msg(recipient[11:], msg)
        elif recipient == 'tweet':
            alert_senders['Twitter'].update_status(msg)
        elif recipient[:4] == 'sms:':
            alert_senders['Twilio'].send_sms(recipient[4:], msg)
        elif recipient[:7] == 'jabber:':
            alert_senders['Jabber'].send_msg(recipient[7:], msg)
        elif recipient[:11] == 'pushbullet:':
            alert_senders['Pushbullet'].send_note(recipient[11:], subject, msg)
        elif recipient[:6] == 'ifttt:':
            alert_senders['IFTTT'].send_trigger(recipient[6:], subject, state, '%d' % (time_in_state))
        elif recipient[:6] == 'spark:':
            alert_senders['CiscoSpark'].send_sparkmsg(recipient[6:], msg)
        elif recipient == 'gcm':
            alert_senders['Gcm'].send_push(state, msg)
        else:
            logger.error("Unrecognized recipient type: %s", recipient)

##############################################################################
# Misc support
##############################################################################

def truncate(input_str, length):
    """Truncate string to specified length

    Args:
        input_str: String to truncate
        length: Maximum length of output string
    """
    if len(input_str) < (length - 3):
        return input_str

    return input_str[:(length - 3)] + '...'

def format_duration(duration_sec):
    """Format a duration into a human friendly string"""
    days, remainder = divmod(duration_sec, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    ret = ''
    if days > 1:
        ret += "%d days " % (days)
    elif days == 1:
        ret += "%d day " % (days)

    if hours > 1:
        ret += "%d hours " % (hours)
    elif hours == 1:
        ret += "%d hour " % (hours)

    if minutes > 1:
        ret += "%d minutes" % (minutes)
    if minutes == 1:
        ret += "%d minute" % (minutes)

    if ret == '':
        ret += "%d seconds" % (seconds)

    return ret


##############################################################################
# Main functionality
##############################################################################
class Door:
    """Contains everything about a door.

     Contains the fixed properties of a door (e.g., which pin it's attached to)
     as well and it's state properties (e.g., whether it's open or closed, and
     when it was last open/closed).
    """
    def __init__(self, door_cfg, initial_state):
        #-- Fixed properties about the door
        self.logger = logging.getLogger(__name__)
        self.pin = door_cfg['pin']
        self.name = door_cfg['name']
        self.recipients = door_cfg['recipients']

        #-- Door state
        self.state = initial_state
        self.time_of_last_state_change = time.time()
        self.alert_still_open_index = 0

class PiGarageAlert(object):
    """Class with main function of Pi Garage Alert"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def main(self):
        """Main functionality
        """

        try:
            # Set up logging
            log_fmt = '%(asctime)-15s %(levelname)-8s %(message)s'
            log_level = logging.INFO

            if sys.stdout.isatty():
                # Connected to a real terminal - log to stdout
                logging.basicConfig(format=log_fmt, level=log_level)
            else:
                # Background mode - log to file
                logging.basicConfig(format=log_fmt, level=log_level, filename=cfg.LOG_FILENAME)

            # Banner
            self.logger.info("==========================================================")
            self.logger.info("Pi Garage Alert starting")

            # Use Raspberry Pi board pin numbers
            self.logger.info("Configuring global settings")
            GPIO.setmode(GPIO.BOARD)

            # Configure the sensor pins as inputs with pull up resistors
            for door in cfg.GARAGE_DOORS:
                self.logger.info("Configuring pin %d for \"%s\"", door['pin'], door['name'])
                GPIO.setup(door['pin'], GPIO.IN, pull_up_down=GPIO.PUD_UP)

            doors = []

            # Create alert sending objects
            alert_senders = {
                "Jabber": Jabber(doors),
                "Twitter": Twitter(),
                "Twilio": Twilio(),
                "Email": Email(),
                "Pushbullet": Pushbullet(),
                "IFTTT": IFTTT(),
                "CiscoSpark": CiscoSpark(),
                "Gcm": GoogleCloudMessaging()
            }

            # Read in door config
            for door_cfg in cfg.GARAGE_DOORS:
                name = door_cfg['name']
                initial_state = get_garage_door_state(door_cfg['pin'])

                doors.append(Door(door_cfg, initial_state))

                self.logger.info("Initial state of \"%s\" is %s",
                                 name, initial_state)

            # Ready to poll and alert!
            # Poll doors every second for updated state
            status_report_countdown = 5
            while True:
                for door in doors:
                    name = door.name
                    state = get_garage_door_state(door.pin)
                    now = time.time()
                    time_in_state = now - door.time_of_last_state_change

                    # Check if the door has changed state
                    if door.state == "closed" and state == "closed":
                        #-- door has remained closed.
                        pass

                    elif door.state == "closed" and state == "open":
                        #-- door has opened!
                        # save new state
                        door.state = state
                        door.time_of_last_state_change = now
                        self.logger.info("State of \"%s\" changed to %s after %.0f sec", name, state, time_in_state)

                        # prepare and send alert
                        now_string = strftime("%Y-%m-%d %H:%M:%S", time.localtime(door.time_of_last_state_change))
                        subject = "%s opening %s" % (door.name, now_string)
                        message = "%s opened at %s" % (door.name, now_string)
                        if time_in_state > 0:
                            message += " (after being closed for " + format_duration(time_in_state) + ")"
                        send_alerts(self.logger, alert_senders, door.recipients,
                                    subject, message, "open", time_in_state)

                    elif door.state == "open" and state == "closed":
                        #-- door has closed!
                        time_opened = door.time_of_last_state_change

                        # save new state
                        door.state = state
                        door.time_of_last_state_change = now
                        self.logger.info("State of \"%s\" changed to %s after %.0f sec", name, state, time_in_state)

                        # prepare and send alert
                        time_opened_string = strftime("%Y-%m-%d %H:%M:%S", time.localtime(time_opened))
                        now_string = strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
                        subject = "%s opening %s" % (door.name, time_opened_string)
                        message = "%s closed at %s (was open for %s)" % (door.name, now_string, format_duration(time_in_state))
                        send_alerts(self.logger, alert_senders, door.recipients,
                                    subject, message, "closed", time_in_state)

                    else:
                        #-- door is still open
                        pass
                #end for doors

                # Periodically log the status for debug and to see if  RPi gets too hot
                status_report_countdown -= 1
                if status_report_countdown <= 0:
                    status_msg = rpi_status()

                    for door in doors:
                        status_msg += \
                            ", %s: %s/%d/%d" % (door.name, door.state, -1,
                                                (time.time() - door.time_of_last_state_change))

                    self.logger.info(status_msg)

                    status_report_countdown = 600

                # Poll every 1 second
                time.sleep(1)
        except KeyboardInterrupt:
            logging.critical("Terminating due to keyboard interrupt")
        except:
            logging.critical("Terminating due to unexpected error: %s", sys.exc_info()[0])
            logging.critical("%s", traceback.format_exc())

        GPIO.cleanup() # pylint: disable=no-member
        alert_senders['Jabber'].terminate()

if __name__ == "__main__":
    PiGarageAlert().main()
