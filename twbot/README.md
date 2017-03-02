    # twtrbot

    - Posts screenshots of specified user's tweets on authenticating user's timeline
    in realtime using the Twitter streaming API.  

    - Marks each tweet as user's original tweet, retweet, reply or delete.  
      - If retweet or reply, captures the tweet's author
      - If a tweet is deleted and the affected tweet was captured, it will repost the screenshot.

    - Characters permitting, the origin tweet will be preserved as much as possible.

    - Can also crawl a specified timeline for past tweets if they fall within the limitations
    of polling a user's timeline.


    [![MIT licensed](https://img.shields.io/badge/license-MIT-blue.svg)](https://raw.githubusercontent.com/emilybarbour/twtrbot/master/LICENSE)


    INSTALLATION
    sudo yum -y update
    sudo yum install -y gcc gcc-c++ automake make openssl-devel kernel-devel git-core freetype-devel fontconfig-devel libpng-devel libjpeg-devel liberation-fonts dejavu-sans-fonts
    sudo rm /usr/bin/python
    sudo ln -s /usr/bin/python2.7 /usr/bin/python
    sudo easy_install-2.7 virtualenv

    https://github.com/creationix/nvm
    sudo ln -s ~/.nvm/versions/node/v7.5.0/bin/node /usr/bin/node

    npm install -g phantomjs-prebuilt
