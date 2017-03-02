# coding: utf-8
import datetime
import json
import logging
import logging.handlers
import requests
import time
from twtrbot import twtrbot
import sys


BOT_NUM=20
logging.addLevelName(BOT_NUM, "BOTLOG")
# Add the log message handler to the logger
LOG_FILENAME = "/home/ec2-user/log/twtrbot.log"
handler = logging.handlers.TimedRotatingFileHandler(LOG_FILENAME, when="d", interval=1, backupCount=14)

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(handler)
LOGGER.setLevel(logging.DEBUG)

class StreamDisconnectError(IOError):
    """ Twitter streams should last forever
        but sometimes do not :( """
    pass

if __name__ == '__main__':
    LOGGER.log(BOT_NUM, 'STARTED BOT AT {}'.format(datetime.datetime.now()))
    json_blob = json.loads(sys.argv[1])
    tweets = twtrbot.TwitterStream(LOGGER, config_file='/home/ec2-user/twtrbot/config.txt', tweet_json=json_blob)
    tweets.post_tweet_json()
