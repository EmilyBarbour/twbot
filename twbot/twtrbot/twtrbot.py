# coding: utf-8
import ast
import contextlib
from datetime import datetime, timedelta
import json
import logging
import logging.handlers
import requests
from requests_oauthlib import OAuth1
import twitter_funcs
import time

BOT_NUM=20
#logging.addLevelName(BOT_NUM, "BOTLOG")
# Add the log message handler to the logger
#LOG_FILENAME = "/home/ec2-user/log/twtrbot.log"
#handler = logging.handlers.TimedRotatingFileHandler(LOG_FILENAME, when="d", interval=1, backupCount=14)

#LOGGER = logging.getLogger(__name__)
#LOGGER.addHandler(handler)
#LOGGER.setLevel(logging.DEBUG)

class StreamDisconnectError(IOError):
    """ Twitter streams should last forever
        but sometimes do not :( """
    pass


class TwitterParseError(Exception):
    """ If tweet response cannot be
        parsed """
    pass


class TwitterStream():

    def __init__(self, logger, config_file='config.txt', daterange=None, tweet_json=None):
        self.HEADERS = {'Accept': 'application/json'}
        self.LOGGER = logger
        self._config(config_file)
        self.last_tweet_time = None
        if daterange:
            self.daterange = daterange
        if tweet_json:
            self.tweet_json = tweet_json

    def _config(self, config_file):
        """ reads in config file for params """

        config = {}
        try:
            with open(config_file, 'r') as config_file:
                for line in config_file:
                    param, value = line.split('=')
                    config[param.strip()] = value.strip()

        except Exception as e:
            self.LOGGER.error('Config File Loading Error: {}', e)
            raise Exception('INVALID CONFIG FILE ({})'.format(e))

        req_params = ['CONSUMER_KEY', 'CONSUMER_SECRET',
                      'TOKEN', 'TOKEN_SECRET',
                      'USER', 'OAUTH_USER']

        if list(set(req_params) - set(config)):
            self.LOGGER.error('Config Params missing: {}'.format(', '.join(list(set(req_params) - set(config)))))
            raise Exception('MISSING PARAMS ({})'.format(', '.join(list(set(req_params) - set(config)))))

        self._auth(config)
        self.user = map(str, ast.literal_eval(config['USER']))
        self.oauth_user = config['OAUTH_USER']

    def api_session(self, retries=15, retry_statuses=[420, 429, 500, 502, 503, 504]):
        """ Get a customized requests Session object. Handle Twitter exceptions """

        session = requests.Session()
        session.headers.update(self.HEADERS)
        retry_config = {
            'logger': self.LOGGER,
            'num_retries': retries,
            'retry_statuses': set(tuple(retry_statuses))
        }

        adapter = requests.adapters.HTTPAdapter(max_retries=3)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def _auth(self, config_dict):
        """ Create a two-legged OAuth1 session object. """

        session = self.api_session()
        session.auth = OAuth1(config_dict['CONSUMER_KEY'], config_dict['CONSUMER_SECRET'],
                              config_dict['TOKEN'], config_dict['TOKEN_SECRET'])

        session.headers.update(self.HEADERS)
        self.session = session

    def start_stream(self):
        """ Start listening to Streaming endpoint. """

        url = "https://stream.twitter.com/1.1/statuses/filter.json"
        params = {'follow': ",".join(self.user)}
        twstream = self.session.post(url, params=params, stream=True)
        self.LOGGER.log(BOT_NUM, 'Connected to Twitter Stream!')
        with contextlib.closing(twstream) as resp:
            for line in resp.iter_lines():
                self.process_stream(line)
            else:
                raise StreamDisconnectError(line)

    def process_stream(self, line):
        """ does stuff w stream output """

        if line:
            tries=0; max=2
            while tries < max:
                try:
                    line = json.loads(line)
                    self.last_tweet_time = twitter_funcs.parse_tweet(self.LOGGER, self.session, self.oauth_user, self.user, self.last_tweet_time, line)
                    break
                except Exception as e:
                    self.LOGGER.error("PARSING ERROR")
                    err = str(e)
                if tries  == max-1:
                    self.LOGGER.log(BOT_NUM, line)
                    self.tweet_json = line
                    self.post_tweet_json()
                    raise TwitterParseError(err)
                tries+=1

    def post_tweet_json(self):
        """ can manually post a json blob """
        self.LOGGER.log(BOT_NUM, "Manually posting json blob")
        twitter_funcs.parse_tweet(self.LOGGER, self.session, self.oauth_user, self.user, self.tweet_json)
        self.LOGGER.log(BOT_NUM, "Manual post successful")

    def get_missing_tweets(self):
        """ gets tweets from user for daterange and compares with tweets posted on timeline user's feed """
        for user in self.user:
            self.LOGGER.log(BOT_NUM, 'Looking for user, {}, missing tweets!  Wish me luck!'.format(user))
            tweets = twitter_funcs.retrieve_historical_tweets(self.session, user, self.daterange)
            if tweets:
                self.LOGGER.log(BOT_NUM, 'There are {} tweets between {} and {}...'.format(len(tweets), self.daterange[0],
                                                                              self.daterange[1]))
                self.post_missing_tweets(user, tweets)
            else:
                self.LOGGER.log(BOT_NUM, 'No missing Tweets. Yay?!')

    def post_missing_tweets(self, user, tweet_list):
        """ posts missing tweets """
        i=0
        for tweet in reversed(tweet_list): # post in chrono order
            if not twitter_funcs.retrieve_tweet(self.session, self.oauth_user, tweet['id_str']):
                tweet['text'] = tweet['text'].encode('utf-8')
                self.LOGGER.log(BOT_NUM, 'Posting missing tweet id: {}, {}'.format(tweet['id_str'], tweet['text']))
                twitter_funcs.parse_tweet(self.LOGGER, self.session, self.oauth_user, user, tweet)
                time.sleep(20) # don't post too fast as to trigger rate limiting
                i+=1

        self.LOGGER.log(BOT_NUM, '{} tweets were missing and posted'.format(i))
