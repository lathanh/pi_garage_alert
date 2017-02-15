#!/usr/bin/python2.7

##############################################################################
# Global settings
##############################################################################

# Describes all the garage doors being monitored
GARAGE_DOORS = [
    {
        'pin': 15,
        'name': "Example Garage Door",
        'recipients' : [
            'sms:+11112223333',
            'email:someone@example.com',
            'twitter_dm:twitter_user',
            'pushbullet:access_token',
            'gcm',
            'tweet',
            'ifttt:garage_door',
            ],
    }
]

# All messages will be logged to stdout and this file
LOG_FILENAME = "/var/log/pi_garage_alert.log"

##############################################################################
# Email settings
##############################################################################

SMTP_SERVER = 'localhost'
SMTP_IS_TLS = False
SMTP_PORT = 25
SMTP_USER = ''
SMTP_PASS = ''
EMAIL_FROM = 'Garage Door <user@example.com>'
EMAIL_PRIORITY = '1'
# 1 High, 3 Normal, 5 Low

##############################################################################
# Cisco Spark settings
##############################################################################

# Obtain your access token from https://developer.ciscospark.com, click
# on your avatar at the top right corner.

SPARK_ACCESSTOKEN = "" #put your access token here between the quotes.

##############################################################################
# Twitter settings
##############################################################################

# Follow the instructions on http://talkfast.org/2010/05/31/twitter-from-the-command-line-in-python-using-oauth/
# to obtain the necessary keys

TWITTER_CONSUMER_KEY = ''
TWITTER_CONSUMER_SECRET = ''
TWITTER_ACCESS_KEY = ''
TWITTER_ACCESS_SECRET = ''

##############################################################################
# Twilio settings
##############################################################################

# Sign up for a Twilio account at https://www.twilio.com/
# then these will be listed at the top of your Twilio dashboard

TWILIO_ACCOUNT = ''
TWILIO_TOKEN = ''

# SMS will be sent from this phone number
TWILIO_PHONE_NUMBER = '+11234567890'

##############################################################################
# Jabber settings
##############################################################################

# Jabber ID and password that status updates will be sent from
# Leave this blank to disable Jabber support

JABBER_ID = ''
JABBER_PASSWORD = ''

# Uncomment to override the default server specified in DNS SRV records

#JABBER_SERVER = 'talk.google.com'
#JABBER_PORT = 5222

# List of Jabber IDs allowed to perform queries

JABBER_AUTHORIZED_IDS = []

##############################################################################
# Google Cloud Messaging settings
##############################################################################

GCM_KEY = ''
GCM_TOPIC = ''

##############################################################################
# IFTTT Maker Channel settings
# Create an applet using the "Maker" channel, pick a event name,
# and use the event name as a recipient of one of the alerts,
# e.g. 'recipients': [ 'ifft:garage_event' ]
#
# Get the key by going to https://ifttt.com/services/maker/settings.
# The key is the part of the URL after https://maker.ifttt.com/use/.
# Do not include https://maker.ifttt.com/use/ in IFTTT_KEY.
##############################################################################

IFTTT_KEY = ''
