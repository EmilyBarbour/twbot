try:
    from cStringIO import StringIO
except:
    from StringIO import StringIO

import contextlib
from datetime import datetime
from dateutil import parser
import json
from functools import wraps
from PIL import Image
import pytz
import requests
from requests_oauthlib import OAuth1
from requests.adapters import HTTPAdapter
from selenium import webdriver
import time


class RetryAdapter(HTTPAdapter):
    """ A requests transport adapter that can retry requests. """

    DEFAULT_RETRY_METHODS = frozenset(['GET', 'POST'])
    BACKOFF_MAX = 180

    def __init__(self, num_retries=0, retry_methods=DEFAULT_RETRY_METHODS,
                 retry_statuses=None, **kwargs):
        self.num_retries = num_retries
        self.retry_methods = retry_methods
        self.retry_statuses = retry_statuses or set()
        super(RetryAdapter, self).__init__(**kwargs)

    def backoff(self, backoff, attempt):
        """ Sleep using an exponential backoff strategy. """

        backoff_time = backoff * (2 ** attempt)
        backoff_time = min(self.BACKOFF_MAX, backoff_time)
        if backoff_time > 0:
            print 'retrying request in {}'.format(backoff_time)
            time.sleep(backoff_time)

    def send(self, request, **kwargs):
        """ Send the request object, retrying if necessary. """

        attempts = 1
        if request.method in self.retry_methods:
            attempts += self.num_retries
        for attempt in range(attempts):
            try:
                response = super(RetryAdapter, self).send(request, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt >= attempts:
                    raise e
                self.backoff(5, attempt)
            else:
                if response.status_code in self.retry_statuses and response.status_code >= 500:
                    self.backoff(5, attempt)
                    continue
                elif response.status_code in self.retry_statuses and response.status_code > 400:
                    print response.text
                    self.backoff(60, attempt)
                    continue
                break
        return response


def api_session(retries=4, retry_statuses=[420, 429, 500, 502, 503, 504]):
        """ Get a customized requests Session object. Handle Twitter exceptions """

        session = requests.Session()
        session.headers.update(headers)
        retry_config = {
            'num_retries': retries,
            'retry_statuses': set(tuple(retry_statuses))
        }

        session.mount('http://', RetryAdapter(**retry_config))
        session.mount('https://', RetryAdapter(**retry_config))
        return session


def create_session(oauth_dict):
    """ Create a two-legged OAuth 1 session object. """

    session = api_session()
    session.auth = OAuth1(oauth_dict['consumer_key'], oauth_dict['consumer_secret'],
                              oauth_dict['access_token'], oauth_dict['token_secret'])

    session.headers.update(headers)
    return session


# In[67]:

def make_request(ses, url, params={}, files={}, method="POST"):
    """ interacts w. internet """

    if method == 'GET':
        resp = ses.get(url, params=params, files=files)

    elif method == 'POST':
        resp = ses.post(url, params=params, files=files)

    resp.raise_for_status()
    resp = resp.json()
    return resp


# In[6]:

def scale_dimensions(dic, size=2):
    """ for mac retina displays """

    for x in dic:
        dic[x] = int(dic[x] * size)
    return dic


# In[7]:

def get_screenshot(tweet_id):
    """ use intents to get screenshot of specific tweet """

    phantomdriver = webdriver.PhantomJS()

    url = "https://twitter.com/intent/like?tweet_id={}".format(tweet_id)
    phantomdriver.get(url)
    phantomdriver.set_window_size(1050, 833) # force desktop view

    fn = str("screenshot-{}.png".format(tweet_id))

    # use javascript to get abs dimensions
    script = "return document.getElementsByClassName(\"tweet-image\")[0].getBoundingClientRect();"
    avatar_dim = phantomdriver.execute_script(script)

    script = "return document.getElementsByClassName(\"tweet-content simple-tweet-content normal \")[0].getBoundingClientRect();"
    tweet_dim = phantomdriver.execute_script(script)

    phantomdriver.save_screenshot(fn) # saves screenshot of entire page
    window_width = float(phantomdriver.get_window_size()["width"]) # get window width
    phantomdriver.quit()

    img = Image.open(fn) # PIL

    # retina displays!
    avatar_dim = scale_dimensions(avatar_dim, size=max(img.size)/window_width)
    tweet_dim = scale_dimensions(tweet_dim, size=max(img.size)/window_width)

    # defines crop points from above elements
    left = avatar_dim['left']
    top = avatar_dim['top']
    right = tweet_dim['right']
    bottom = tweet_dim['bottom']

    img = img.crop((left, top, right, bottom))

    img.save(fn) # saves new cropped image
    return fn


def coerce_date(date_object):
    """ takes a date object and ensures it is a datetime.date object """

    if isinstance(date_object, (unicode, str)):
        return parser.parse(date_object).date()
    elif isinstance(date_object, datetime.datetime):
        return date_object.date()
    else:
        return date_object


def walk_timeline(ses, user_id, tweet_id=None, filter_user=True, max_pages=30):
    """ traverse timeline of specific user """

    url = "https://api.twitter.com/1.1/statuses/user_timeline.json"
    params = {"user_id": user_id, "include_rts": "true",
              "count": 200}

    if tweet_id:
        params["since_id"] = tweet_id

    p=0
    while p < max_pages:
        resp = make_request(ses, url, params=params, method="GET")
        if filter_user:
            tweets = [i for i in resp if "user" in i and i["user"]["id_str"]==user_id and "text" in i]
            yield tweets
        else:
            yield resp
        if resp and (params["max_id"] != resp[-1]['id'] if 'max_id' in params else True):
            params["max_id"] = resp[-1]["id"]
            p+=1
        else:
            p = max_pages


def retrieve_tweet(session, user_id, tweet_id, pages=30):
    """ tries to retrieve specified tweet json from authenticating user's timeline """

    timeline = walk_timeline(session, user_id, tweet_id=tweet_id, max_pages=pages)

    for page in timeline:
        tweet = [i for i in page if "user" in i and i["user"]["id_str"]==user_id and "text" in i and tweet_id in i["text"]]
        if tweet and 'entities' in tweet[0]:
            return tweet[0]
    return []


def retrieve_historical_tweets(session, user_id, daterange, pages=30):
    """ retrieves tweets for a specific timeframe """

    start, end = daterange
    start = coerce_date(start)
    end = coerce_date(end)

    tweets = []
    timeline = walk_timeline(session, user_id, max_pages=pages)
    for page in timeline:
        tweet = [i for i in page if "created_at" in i and (start <= conv_from_utc(datetime.strptime(i["created_at"].replace('+0000 ', ''), '%a %b %d %H:%M:%S %Y'), force=True).date() <= end) and "text" in i]
        if tweet:
            tweets.extend(tweet)
        if page and conv_from_utc(datetime.strptime(page[-1]['created_at'].replace('+0000 ', ''), '%a %b %d %H:%M:%S %Y'), force=True).date() < start:
            break
    return tweets


def get_tweet(ses, tweet_id):
    """ retrieves individual tweet """

    url = "https://api.twitter.com/1.1/statuses/show.json"
    params = {"id": tweet_id, "include_entities": "true"}
    resp = make_request(ses, url, params=params, files={}, method="GET")
    return resp


def download_image(ses, url):
    """ dumps image into memory """

    dl = ses.get(url, stream=True)
    img = StringIO()
    img.write(dl.content)
    img.seek(0) # rewind to beginning
    return img


def upload_screenshot(ses, fn):
    """ uploads screenshot to tw """

    url = "https://upload.twitter.com/1.1/media/upload.json"
    if isinstance(fn, (basestring, unicode)):
        payload = {"media": open(fn, "rb")}
        payload["media"] = payload["media"].read()
    else:
        payload = {"media": fn}

    resp = make_request(ses, url, files=payload)
    if "image" in resp:
        return resp["media_id_string"]
    else:
        print "MEDIA ID NOT FOUND"
        print resp


def conv_from_utc(naive, timezone="America/New_York", force=False):
    """ Converts UTC to timezone """

    if not datetime.now().strftime('%Y-%m-%d %H:%M:%S') == datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S') and not force:
        return naive
    naive = naive.replace(tzinfo=pytz.UTC)
    local_dt = naive.astimezone(pytz.timezone("America/New_York"))
    return local_dt


def get_media(ses, tweet, capture=3):
    """ gets media from existing tweet and posts it to twitter """
    if "media" in tweet["entities"]:
        media_id_list = []
        urls = [i["media_url_https"] if "media_url_https" in i else i["media_url"] for i in tweet["entities"]["media"]][0: capture]
        for url in urls:
            media_id_list.append(upload_screenshot(ses, download_image(ses, url)))
        return media_id_list
    return []


def get_entities(ses, tweet, capture=3):
    """ retrieves tweet entities """
    urls = []; media_ids = []
    if "entities" in tweet:
        media_ids = get_media(ses, tweet, capture=capture)
        urls = [i["expanded_url"] for i in tweet["entities"]["urls"] if "urls" in tweet["entities"] and "expanded_url" in i]
    return urls, media_ids


def compose_tweet(media_id=None, data={}):
    """ writes tweet """

    if data["status"] == "tweeted":
        status = ".@{} tweeted @ {} (#{})".format(data["user"], data["timestamp"], data["tweet_id"])

    elif data["status"] in ["retweeted", "replied to"]:
        status = ".@{} {} @{} @ {} (#{})".format(data["user"], data["status"], data["original_user"],
                                                 data["timestamp"], data["tweet_id"])

    else: # deleted
        if "user" in data:
            status = "{} {} tweet #{} @ {}".format(data["user"], data["status"], data["tweet_id"], data["timestamp"])
        else:
            status = "Tweet ID, #{}, was deleted @ {}".format(data["tweet_id"], data["timestamp"])

    if "urls" in data and data["urls"]:
        for url in data["urls"]:
            if len(status) + min(23, len(url)) + 2 + (23 if media_id else 0) <= 140:
                status += "\n{}".format(url)

    if len(status) > 140:
        status = status[0: 139]

    params = {"status": status}
    if media_id:
        params["media_ids"] = media_id
    return params


def send_tweet(ses, params):
    """ posts tweet """

    url = "https://api.twitter.com/1.1/statuses/update.json"
    make_request(ses, url, params=params)


def parse_tweet(session, user, tweet):
    if "user" in tweet and tweet["user"]["id_str"] == user: # filter tweets/rts to user
        media_ids = []
        data = {"tweet_id": tweet["id_str"], "user": tweet["user"]["screen_name"]}

        if "retweeted_status" in tweet and tweet["retweeted_status"]:
            data["status"] = "retweeted"
            data["original_tweet_id"] = tweet["retweeted_status"]["id"]
            data["original_user"] = tweet["retweeted_status"]["user"]["screen_name"]
            data["urls"], media = get_entities(session, tweet["retweeted_status"], capture=3)
            if media:
                media_ids.extend(media)

        elif "in_reply_to_screen_name" in tweet and tweet["in_reply_to_screen_name"]:
            data["status"] = "replied to"
            data["original_tweet_id"] = tweet["in_reply_to_status_id_str"]
            data["original_user"] = tweet["in_reply_to_screen_name"]
            # get original tweet
            fn = get_screenshot(data["original_tweet_id"])
            media_ids.append(upload_screenshot(session, fn))
            # get original media
            original = get_tweet(session, data["original_tweet_id"])
            data["urls"], media = get_entities(session, original, capture=2)
            if media:
                media_ids.extend(media)
        else:
            data["status"] = "tweeted"
            data["urls"], media = get_entities(session, tweet, capture=3)
            if media:
                media_ids.extend(media)

        if "timestamp_ms" in tweet:
            ts = conv_from_utc(datetime.fromtimestamp(float(tweet["timestamp_ms"])/1000.0))
            data["timestamp"] = "{} on {}".format(ts.strftime("%I:%M:%S %p"), ts.strftime("%m/%d/%y"))
        elif 'created_at' in tweet:
            ts = conv_from_utc(datetime.strptime(tweet['created_at'].replace('+0000 ', ''), '%a %b %d %H:%M:%S %Y'), force=True)
            data["timestamp"] = "{} on {}".format(ts.strftime("%I:%M:%S %p"), ts.strftime("%m/%d/%y"))

        fn = get_screenshot(data["tweet_id"])
        media_id = upload_screenshot(session, fn)
        if media_ids:
            media_id = ",".join([media_id] + media_ids)
        params = compose_tweet(media_id=media_id, data=data)
        send_tweet(session, params)

    elif "delete" in tweet:
        ts = conv_from_utc(datetime.fromtimestamp(float(tweet["delete"]["timestamp_ms"])/1000.0))
        tweet_id = tweet["delete"]["status"]["id_str"]
        deleted_tweet = retrieve_tweet(session, user_id, tweet_id, max_pages=30)

        data = {"tweet_id": tweet_id,
                "timestamp": "{} on {}".format(ts.strftime("%I:%M:%S %p"), ts.strftime("%m/%d/%y"))}

        if deleted_tweet:
            data["user"] = deleted_tweet["text"].split()[0]
            if "replied" in deleted_tweet["text"]:
                data["status"] = "deleted reply of"
            elif "retweeted" in deleted_tweet["text"]:
                data["status"] = "deleted retweet of"
            else:
                data["status"] = "deleted"
            media_id = get_media(session, deleted_tweet, capture=1)
            if media_id:
                media_id = media_id[0]
        else:
            media_id = None
            data["status"] = "deleted"
        params = compose_tweet(media_id=media_id, data=data)
        send_tweet(session, params)


# In[86]:

dj = "25073877"
em = "371245814"
obot = "803105991936057344"

user = em
user_id = obot


# In[59]:

tids = ["809803893920165892"]
for tid in tids:
    tweet = get_tweet(tid)
    parse_tweet(tweet)


# In[40]:

def post_rt(rt_id):
    rt = get_tweet(rt_id)
    # get random tweet from user
    tweet = get_tweet("808787048144453632")
    tweet["retweeted_status"] = rt
    tweet["id_str"] = rt["id_str"]
    tweet["created_at"] = rt["created_at"]
    parse_tweet(tweet)


class TwitterStream():

    def __init__(self, config_file='config.txt', daterange=None):
        self.HEADERS = {'Accept': 'application/json'}
        self._config(config_file)
        if daterange:
            self.daterange = daterange

    def _config(self, config_file):
        """ reads in config file for params """

        config = {}
        try:
            with open(config_file, 'r') as config_file:
                for line in config_file:
                    param, value = line.split('=')
                    config[param.strip()] = value.strip()
        except Exception as e:
            raise Exception('INVALID CONFIG FILE ({})'.format(e))

        req_params = ['CONSUMER_KEY','CONSUMER_SECRET','TOKEN','TOKEN_SECRET',
                      'USER', 'OAUTH_USER']

        if list(set(req_params) - set(config)):
            raise Exception('MISSING PARAMS ({})'.format(', '.join(list(set(req_params) - set(config)))))

        self._auth(config)
        self.user = config['USER']
        self.oauth_user = config['OAUTH_USER']

    def api_session(self, retries=4, retry_statuses=[420, 429, 500, 502, 503, 504]):
        """ Get a customized requests Session object. Handle Twitter exceptions """

        session = requests.Session()
        session.headers.update(self.HEADERS)
        retry_config = {
            'num_retries': retries,
            'retry_statuses': set(tuple(retry_statuses))
        }

        session.mount('http://', RetryAdapter(**retry_config))
        session.mount('https://', RetryAdapter(**retry_config))
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
        params = {"follow": self.user}
        twstream = self.session.post(url, params=params, stream=True)
        with contextlib.closing(twstream) as resp:
            for line in resp.iter_lines():
                self.process_stream(line)


    def process_stream(self, line):
        """ does stuff w stream output """

        if line:
            line = json.loads(line)
            parse_tweet(self.session, self.user, line)

    def get_missing_tweets(self):
        """ gets tweets from user for daterange and compares with tweets posted on timeline user's feed """

        tweets = retrieve_historical_tweets(self.session, self.user, self.daterange, pages=40)
        if tweets:
            print 'There are {} missing tweets...'.format(len(tweets))
            self.post_missing_tweets(tweets)


    def post_missing_tweets(self, tweet_list):
        """ posts missing tweets """
        for tweet in reversed(tweet_list):
            if not retrieve_tweet(self.session, self.oauth_user, tweet['id_str'], pages=30):
                parse_tweet(self.session, self.user, tweet)
                time.sleep(30) # don't post too fast to trigger rate limiting
