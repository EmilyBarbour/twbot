# coding: utf-8
import datetime
import logging
import logging.handlers
import requests
import time
from twtrbot import twtrbot

BOT_NUM=25
logging.addLevelName(BOT_NUM, "BOTLOG")
# Add the log message handler to the logger
LOG_FILENAME = "/home/ec2-user/log/twtrbot.log"
handler = logging.handlers.TimedRotatingFileHandler(LOG_FILENAME, when="d", interval=1, backupCount=14)

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(handler)
LOGGER.setLevel(logging.DEBUG)


class StreamDisconnectError(IOError):
    """ Twitter streams should last forever
        but sometimes does not :( """
    pass


def check_retries(tries):
    if tries > 5:
        return False
    return True

if __name__ == '__main__':
    LOGGER.log(BOT_NUM, 'STARTED BOT AT {}'.format(datetime.datetime.now()))
    tweets = twtrbot.TwitterStream(LOGGER, config_file='/home/ec2-user/twtrbot/config.txt')
    retries = 1
    x = True
    while x:
        try:
            tweets.start_stream()
        except requests.HTTPError:
            LOGGER.warning('An HTTP error occurred.')
            time.sleep(min(5**retries, 320))
            retries+=1
            x = check_retries(retries)
        except StreamDisconnectError:
            LOGGER.warning('The stream died.')
            time.sleep(60**retries)
            retries+=1
            x = check_retries(retries)
        except Exception as e:
            LOGGER.warning('Some other error occured')
            LOGGER.warning(str(e))
            time.sleep(30**retries)
            retries+=1
            x = check_retries(retries)
    if not x:
        LOGGER.error('Max retries attempted')
