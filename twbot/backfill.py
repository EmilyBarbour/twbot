# coding: utf-8
from datetime import datetime, timedelta
import logging
import logging.handlers
from twtrbot import twtrbot

BOT_NUM=20
logging.addLevelName(BOT_NUM, "BOTLOG")
# Add the log message handler to the logger
LOG_FILENAME = "/home/ec2-user/log/twtrbot-backfill.log"
handler = logging.handlers.TimedRotatingFileHandler(LOG_FILENAME, when="d", interval=1, backupCount=14)

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(handler)
LOGGER.setLevel(logging.DEBUG)

if __name__ == '__main__':
    tweets = twtrbot.TwitterStream(LOGGER, config_file='/home/ec2-user/twtrbot/config.txt', daterange=(datetime.now().date() - timedelta(1), datetime.now().date()))
    tweets.get_missing_tweets()
