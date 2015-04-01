#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Spell corrector - http://www.chiodini.org/
# Copyright © 2015 Luca Chiodini <luca@chiodini.org>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import codecs
import html
import json
import logging
import os
import random
import redis
import requests
import string
import tempfile
import time

from collections import Counter
from datetime import datetime
from subprocess import call

REDIS_UNIGRAMS_DB = 0
REDIS_BIGRAMS_DB = 1
URL = 'http://it.wikipedia.org/'
logger = logging.getLogger()


class MediaWiki:

    def __init__(self, base_URL):
        # Try to ease the interface fixing common URL mistakes.
        if not base_URL.endswith('w/api.php'):
            if not base_URL[-1] == '/':
                base_URL += '/'
            base_URL += 'w/api.php'
        self.base_URL = base_URL

    def getRecentChanges(self, start_from, last_id=0, namespace=0):

        # Get from_time in the YYYYMMDDHHMMSS format, as required by MediaWiki.
        start_from_str = start_from.strftime('%Y%m%d%H%M%S')

        parameters = {'action': 'query',
                      'format': 'json',
                      'list': 'recentchanges',
                      'continue': '',
                      'rcnamespace': namespace,
                      'rcstart': start_from_str,
                      'rcdir': 'newer',
                      'rclimit': 500,  # maximum
                      'rcprop': 'ids|timestamp'}
        r = requests.get(self.base_URL, params=parameters).json()
        recentchanges = r['query']['recentchanges']
        recentchanges = [rc for rc in recentchanges if rc['rcid'] > last_id]
        return recentchanges

    def getPageReviews(self, revIDs):
        # Return None for an empty list.
        if not revIDs:
            return None

        # Build a string in the form ID-1|ID-2|...|ID-N.
        revIDs_string = ""
        for ID in revIDs:
            revIDs_string += str(ID) + "|"
        # Remove the trailing pipe.
        revIDs_string = revIDs_string[:-1]

        parameters = {'action': 'query',
                      'format': 'json',
                      'prop': 'revisions',
                      'rvprop': 'content',
                      'revids': revIDs_string}
        r = requests.get(self.base_URL, params=parameters).json()
        response = []
        page = next(iter(r['query']['pages'].values()))
        try:
            for revision in page['revisions']:
                response.append({'content': html.escape(revision['*']),
                                 'pageid': page['pageid'],
                                 'title': page['title']
                                 })
        # Silently ignore any kind of error (e.g., deleted page which do not
        # have attributes we'd like to retrieve)
        except KeyError:
            pass
        return response


def update_redis_key(redis, key, delta):
    # Redis transaction.
    with redis.pipeline() as pipe:
        while 1:
            try:
                pipe.watch(key)
                current_value = pipe.get(key)
                if current_value is None:
                    current_value = 0
                next_value = int(current_value) + delta
                pipe.multi()
                pipe.set(key, next_value)
                pipe.execute()
                break
            except WatchError:
                continue


def execute():

    # Try to read the config file with initial values.
    start_from = datetime.min
    last_id = 0
    try:
        with open('updateWikiData.conf', 'r') as conf_file:
            conf = json.loads(conf_file.read())
            start_from = datetime.strptime(conf['start_from'], '%Y%m%d%H%M%S')
            last_id = conf['last_id']
            redis_host = conf['redis_host']
    except FileNotFoundError:
        logger.warning("No config file found. Using default values.")
    except (KeyError, ValueError):
        logger.warning("Corrupted config file. Using default values.")

    mediaWiki = MediaWiki(URL)

    # Initialize new config values (it must be done here as we want to store
    # the right date and time we made the request).
    new_start_from = datetime.min
    new_last_id = 0

    tmp = mediaWiki.getRecentChanges(start_from, last_id)
    print(len(tmp))

    # Create a temporary workspace.
    temp_env = tempfile.TemporaryDirectory()
    path = temp_env.name

    # Write XML header.
    with open(path + '/old.xml', 'w', encoding='utf-8') as f:
        f.write("<mediawiki>")
        f.write("<base>" + URL + "wiki" + "</base>")
    with open(path + '/new.xml', 'w', encoding='utf-8') as f:
        f.write("<mediawiki>")
        f.write("<base>" + URL + "wiki" + "</base>")

    if len(tmp) == 0:
        return 0

    # Write XML body.
    for item in tmp:
        print(item['revid'])
        print(item['old_revid'])

        # TODO This means that the page has been deleted or added
        # Should cover these corner cases too.
        if item['type'] != 'edit':
            continue

        revs = mediaWiki.getPageReviews([item['revid'], item['old_revid']])

        if len(revs) != 2:
            logger.warning("Ignoring revisions " + str(item['revid']) + " and "
                           + str(item['old_revid']) + " (bad API response).")
            continue

        # Update new_last_id and new_start_from.
        new_last_id = max(new_last_id, item['rcid'])

        new_start_from = max(new_start_from,
                             datetime.strptime(item['timestamp'],
                                               '%Y-%m-%dT%H:%M:%SZ'))

        # Create XML files.

        filename = ''.join([random.choice(string.ascii_letters)
                           for _ in range(16)])

        # Open in append mode.
        with open(path + '/old.xml', 'a', encoding='utf-8') as f:
            f.write("<page>")
            f.write("<title>" + revs[0]['title'] + "</title>")
            f.write("<id>" + str(revs[0]['pageid']) + "</id>")
            f.write("<revision>")
            f.write("<id>" + str(item['old_revid']) + "</id>")
            f.write("<text>" + revs[0]['content'] + "</text>")
            f.write("</revision></page>")

        with open(path + '/new.xml', 'a', encoding='utf-8') as f:
            f.write("<page>")
            f.write("<title>" + revs[1]['title'] + "</title>")
            f.write("<id>" + str(revs[1]['pageid']) + "</id>")
            f.write("<revision>")
            f.write("<id>" + str(item['revid']) + "</id>")
            f.write("<text>" + revs[1]['content'] + "</text>")
            f.write("</revision></page>")

    # Write XML footer (open files in append mode)
    with open(path + '/old.xml', 'a', encoding='utf-8') as f:
        f.write("</mediawiki>")
    with open(path + '/new.xml', 'a', encoding='utf-8') as f:
        f.write("</mediawiki>")

    # Execute WikiExtractor to clean WikiText syntax.
    # These two calls should produce old.raw and new.raw.
    # TODO Catch exceptions.

    call(["./WikiExtractorMT.py", "-fplain", "-o" + path + "/old.raw",
          path + "/old.xml", ""])
    call(["./WikiExtractorMT.py", "-fplain", "-o" + path + "/new.raw",
          path + "/new.xml", ""])

    # Execute computeFrequencies to get {old, new}.{unigrams, bigrams}
    # frequencies.
    # TODO Catch exceptions.

    if item['old_revid'] > 0:
        call(["./computeFrequencies.py", "-tunigrams",
              "-f" + path + "/old.raw", "-o" + path + "/old.unigrams"])
    call(["./computeFrequencies.py", "-tunigrams",
          "-f" + path + "/new.raw", "-o" + path + "/new.unigrams"])
    if item['old_revid'] > 0:
        call(["./computeFrequencies.py", "-tbigrams",
              "-f" + path + "/old.raw", "-o" + path + "/old.bigrams"])
    call(["./computeFrequencies.py", "-tbigrams",
          "-f" + path + "/new.raw", "-o" + path + "/new.bigrams"])

    # Compute delta frequencies between {old, new}.unigrams and store them in a
    # python Counter.

    uni_redis = redis.StrictRedis(host=conf['redis_host'], port=6379,
                                  db=REDIS_UNIGRAMS_DB)
    uni_counter = Counter()

    with codecs.open(path + '/old.unigrams', 'r', 'utf8') as f:
        lines = 0
        for line in f:
            if lines > 0:  # skip first line (which is the header)
                vals = line.rsplit(' ', 1)
                # Subtract old values.
                uni_counter[vals[0]] -= int(vals[1])
            lines += 1
    with codecs.open(path + '/new.unigrams', 'r', 'utf8') as f:
        lines = 0
        for line in f:
            if lines > 0:  # skip first line (which is the header)
                vals = line.rsplit(' ', 1)
                # Add new values.
                uni_counter[vals[0]] += int(vals[1])
            lines += 1

    # Compute delta frequencies between {old, new}.bigrams and store them in a
    # python Counter.

    bi_redis = redis.StrictRedis(host=conf['redis_host'], port=6379,
                                 db=REDIS_BIGRAMS_DB)
    bi_counter = Counter()

    with codecs.open(path + '/old.bigrams', 'r', 'utf8') as f:
        lines = 0
        for line in f:
            if lines > 0:  # skip first line (which is the header)
                vals = line.rsplit(' ', 1)
                # Subtract old values.
                uni_counter[vals[0]] -= int(vals[1])
            lines += 1
    with codecs.open(path + '/new.bigrams', 'r', 'utf8') as f:
        lines = 0
        for line in f:
            if lines > 0:  # skip first line (which is the header)
                vals = line.rsplit(' ', 1)
                # Add new values.
                uni_counter[vals[0]] += int(vals[1])
            lines += 1

    # Send unigrams data to redis.
    for key, delta in uni_counter.items():
        # Skip trivial items.
        if delta != 0:
            update_redis_key(uni_redis, key, delta)

    # Send bigrams data to redis
    for key, delta in bi_counter.items():
        # Skip trivial items.
        if delta != 0:
            update_redis_key(bi_redis, key, delta)

    # Cleanup temporary data.
    temp_env.cleanup()

    # Try to write config file with new values.
    with open('updateWikiData.conf', 'w') as conf_file:
        conf = {'start_from': new_start_from.strftime('%Y%m%d%H%M%S'),
                'last_id': new_last_id,
                'redis_host': redis_host}
        conf_file.write(json.dumps(conf))


def main():
    # Loop forever and execute the core program with these settings:
    # - Do not launch concurrent request
    # - Wait (at least) 60 seconds between two requests
    # - If a request takes longer than 60 seconds, start the following one
    #   as soon as possible.
    while True:
        begin = time.time()
        execute()
        if (time.time() - begin < 60.0):
            time.sleep(60.0 - (time.time() - begin))


if __name__ == '__main__':
    main()
