try:
    from cStringIO import StringIO
except:
    from StringIO import StringIO

from datetime import datetime
from dateutil import parser
import logging
import logging.handlers
from PIL import Image
import pytz
import requests
from requests.adapters import HTTPAdapter
from selenium import webdriver
import time

BOT_NUM=20
#logging.addLevelName(BOT_NUM, "BOTLOG")
# Add the log message handler to the logger
#LOG_FILENAME = "/home/ec2-user/log/twtrbot.log"
#handler = logging.handlers.TimedRotatingFileHandler(LOG_FILENAME, when="d", interval=1, backupCount=14)

#LOGGER = logging.getLogger(__name__)
#LOGGER.addHandler(handler)


def make_request(session, url, params={}, files={}, method='POST'):
    """ http requests """

    if method == 'GET':
        resp = session.get(url, params=params, files=files)

    elif method == 'POST':
        resp = session.post(url, params=params, files=files)

    resp.raise_for_status()
    resp = resp.json()
    return resp


def scale_dimensions(dic, size=2):
    """ for mac retina displays """

    for x in dic:
        dic[x] = int(dic[x] * size)
    return dic


def get_screenshot(tweet_id):
    """ use intents to get screenshot of specific tweet """

    phantomdriver = webdriver.PhantomJS()

    url = 'https://twitter.com/intent/like?tweet_id={}'.format(tweet_id)
    phantomdriver.get(url)
    phantomdriver.set_window_size(1050, 833) # force desktop view

    fn = str('screenshot-{}.png'.format(tweet_id))

    # use javascript to get abs dimensions
    script = 'return document.getElementsByClassName(\'tweet-image\')[0].getBoundingClientRect();'
    avatar_dim = phantomdriver.execute_script(script)

    script = 'return document.getElementsByClassName(\'tweet-content simple-tweet-content normal \')[0].getBoundingClientRect();'
    tweet_dim = phantomdriver.execute_script(script)

    phantomdriver.save_screenshot(fn) # saves screenshot of entire page
    window_width = float(phantomdriver.get_window_size()['width']) # get window width
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
    elif isinstance(date_object, datetime):
        return date_object.date()
    else:
        return date_object


def walk_timeline(ses, user_id, tweet_id=None, filter_user=True, max_pages=30):
    """ traverse timeline of specific user """

    url = 'https://api.twitter.com/1.1/statuses/user_timeline.json'
    params = {'user_id': user_id, 'include_rts': 'true',
              'count': 200}

    if tweet_id:
        params['since_id'] = tweet_id

    p=0
    while p < max_pages:
        resp = make_request(ses, url, params=params, method='GET')
        if filter_user:
            tweets = [i for i in resp if 'user' in i and i['user']['id_str']==user_id]
            yield tweets
        else:
            yield resp
        if resp and (params['max_id'] != resp[-1]['id'] if 'max_id' in params else True):
            params['max_id'] = resp[-1]['id']
            p+=1
        else:
            p = max_pages


def retrieve_tweet(session, user_id, tweet_id, pages=30):
    """ tries to retrieve specified tweet json from authenticating user's timeline """

    timeline = walk_timeline(session, user_id, tweet_id=tweet_id, max_pages=pages)

    for page in timeline:
        tweet = [i for i in page if 'user' in i and i['user']['id_str']==user_id and 'text' in i and tweet_id in i['text']]
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
        tweet = [i for i in page if 'created_at' in i and (start <= conv_from_utc(datetime.strptime(i['created_at'].replace('+0000 ', ''), '%a %b %d %H:%M:%S %Y'), force=True).date() <= end) and 'text' in i]
        if tweet:
            tweets.extend(tweet)
        if page and conv_from_utc(datetime.strptime(page[-1]['created_at'].replace('+0000 ', ''), '%a %b %d %H:%M:%S %Y'), force=True).date() < start:
            break
    return tweets


def get_tweet(session, tweet_id):
    """ retrieves individual tweet """

    url = 'https://api.twitter.com/1.1/statuses/show.json'
    params = {'id': tweet_id, 'include_entities': 'true'}
    resp = make_request(session, url, params=params, files={}, method='GET')
    return resp


def download_image(session, url):
    """" dumps image into memory """

    dl = session.get(url, stream=True)
    img = StringIO()
    img.write(dl.content)
    img.seek(0) # rewind to beginning
    return img


def upload_screenshot(LOGGER, session, fn):
    """ uploads screenshot to tw """

    url = 'https://upload.twitter.com/1.1/media/upload.json'
    if isinstance(fn, (basestring, unicode)):
        payload = {'media': open(fn, 'rb')}
        payload['media'] = payload['media'].read()
    else:
        payload = {'media': fn}

    resp = make_request(session, url, files=payload)
    if 'image' in resp:
        return resp['media_id_string']
    else:
        LOGGER.error('Media ID not found')
        LOGGER.debug(resp.text)


def conv_from_utc(naive, timezone='America/New_York', force=False):
    """ Converts UTC to timezone """

    if not datetime.now().strftime('%Y-%m-%d %H:%M:%S') == datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S') and not force:
        return naive
    naive = naive.replace(tzinfo=pytz.UTC)
    local_dt = naive.astimezone(pytz.timezone(timezone))
    return local_dt


def get_media(LOGGER, session, tweet, capture=3):
    """ gets media from existing tweet and posts it to twitter """
    if 'media' in tweet['entities']:
        media_id_list = []
        urls = [i['media_url_https'] if 'media_url_https' in i else i['media_url'] for i in tweet['entities']['media']][0: capture]
        for url in urls:
            media_id_list.append(upload_screenshot(LOGGER, session, download_image(session, url)))
        return media_id_list
    return []


def get_entities(LOGGER, session, tweet, capture=3):
    """ retrieves tweet entities """
    urls = []; media_ids = []
    if 'entities' in tweet:
        media_ids = get_media(LOGGER, session, tweet, capture=capture)
        urls = [i['expanded_url'] for i in tweet['entities']['urls'] if 'urls' in tweet['entities'] and 'expanded_url' in i]
    return urls, media_ids


def compose_tweet(media_id=None, data={}):
    """ writes tweet """

    if data['status'] == 'tweeted':
        status = '.@{} tweeted @ {} (#{})'.format(data['user'], data['timestamp'], data['tweet_id'])

    elif data['status'] in ['retweeted', 'replied to']:
        status = '.@{} {} @{} @ {} (#{})'.format(data['user'], data['status'], data['original_user'],
                                                 data['timestamp'], data['tweet_id'])

    else: # deleted
        if 'user' in data:
            status = '{} {} tweet #{} @ {}'.format(data['user'], data['status'], data['tweet_id'], data['timestamp'])
        else:
            status = 'Tweet ID, #{}, was deleted @ {}'.format(data['tweet_id'], data['timestamp'])

    status += " #MAGA"
    if 'urls' in data and data['urls']:
        for url in data['urls']:
            if len(status) + min(23, len(url)) + 2 + (23 if media_id else 0) <= 140:
                status += '\n{}'.format(url)

    if len(status) > 140:
        status = status[0:139]

    params = {'status': status}
    if media_id:
        params['media_ids'] = media_id
    return params


def send_tweet(session, params):
    """" posts tweet """

    url = 'https://api.twitter.com/1.1/statuses/update.json'
    make_request(session, url, params=params)


def parse_tweet(LOGGER, session, oauth_user, user, last_tweet_time, tweet):
    """ parses tweet json and reposts it """

    if 'user' in tweet and tweet['user']['id_str'] in user: # filter tweets/rts to user
        media_ids = []
        data = {'tweet_id': tweet['id_str'], 'user': tweet['user']['screen_name']}

        if 'retweeted_status' in tweet and tweet['retweeted_status']:
            data['status'] = 'retweeted'
            data['original_tweet_id'] = tweet['retweeted_status']['id']
            data['original_user'] = tweet['retweeted_status']['user']['screen_name']
            data['urls'], media = get_entities(LOGGER, session, tweet['retweeted_status'], capture=3)
            if media:
                media_ids.extend(media)

        elif 'in_reply_to_screen_name' in tweet and tweet['in_reply_to_screen_name'] \
        and 'in_reply_to_status_id_str' in tweet and tweet['in_reply_to_status_id_str']:
            data['status'] = 'replied to'
            data['original_tweet_id'] = tweet['in_reply_to_status_id_str']
            data['original_user'] = tweet['in_reply_to_screen_name']
            # get original tweet
            fn = get_screenshot(data['original_tweet_id'])
            media_ids.append(upload_screenshot(LOGGER, session, fn))
            # get original media
            original = get_tweet(session, data['original_tweet_id'])
            data['urls'], media = get_entities(LOGGER, session, original, capture=2)
            if media:
                media_ids.extend(media)
        else:
            data['status'] = 'tweeted'
            data['urls'], media = get_entities(LOGGER, session, tweet, capture=3)
            if media:
                media_ids.extend(media)

        if 'timestamp_ms' in tweet:
            ts = conv_from_utc(datetime.fromtimestamp(float(tweet['timestamp_ms'])/1000.0))
            data['timestamp'] = '{} on {}'.format(ts.strftime('%I:%M:%S %p'), ts.strftime('%m/%d/%y'))
        elif 'created_at' in tweet:
            ts = conv_from_utc(datetime.strptime(tweet['created_at'].replace('+0000 ', ''), '%a %b %d %H:%M:%S %Y'), force=True)
            data['timestamp'] = '{} on {}'.format(ts.strftime('%I:%M:%S %p'), ts.strftime('%m/%d/%y'))

        fn = get_screenshot(data['tweet_id'])
        media_id = upload_screenshot(LOGGER, session, fn)
        if media_ids:
            media_id = ','.join([media_id] + media_ids)
        params = compose_tweet(media_id=media_id, data=data)
        if last_tweet_time and last_tweet_time >= datetime.now() - timedelta(seconds=20):
            time.sleep((datetime.now() - timedelta(20)).second - last_tweet_time.second)
        send_tweet(session, params)
        return datetime.now()

    elif 'delete' in tweet:
        LOGGER.log(BOT_NUM, 'Tweet {} was deleted'.format(tweet['delete']['status']['id_str']))
        ts = conv_from_utc(datetime.fromtimestamp(float(tweet['delete']['timestamp_ms'])/1000.0))
        tweet_id = tweet['delete']['status']['id_str']
        LOGGER.log(BOT_NUM, 'Retrieving deleted tweet from oauth user\'s timeline')
        deleted_tweet = retrieve_tweet(session, oauth_user, tweet_id, pages=30)
        data = {'tweet_id': tweet_id,
                'timestamp': '{} on {}'.format(ts.strftime('%I:%M:%S %p'), ts.strftime('%m/%d/%y'))}

        if deleted_tweet:
            LOGGER.log(BOT_NUM, 'Deleted tweet retrieved!')
            data['user'] = deleted_tweet['text'].split()[0]
            if 'replied' in deleted_tweet['text']:
                data['status'] = 'deleted reply of'
            elif 'retweeted' in deleted_tweet['text']:
                data['status'] = 'deleted retweet of'
            else:
                data['status'] = 'deleted'
            media_id = get_media(LOGGER, session, deleted_tweet, capture=1)
            if media_id:
                media_id = media_id[0]
        else:
            media_id = None
            data['status'] = 'deleted'
        params = compose_tweet(media_id=media_id, data=data)

        LOGGER.log(BOT_NUM, 'Posting tweet status type: {}, tweet id: {} from @{}'.format(data['status'],  data['tweet_id'], data['user']))
        if last_tweet_time and last_tweet_time >= datetime.now() - timedelta(seconds=20):
            time.sleep((datetime.now() - timedelta(20)).second - last_tweet_time.second)
        send_tweet(session, params)
        return datetime.now()
    else:
        return None
