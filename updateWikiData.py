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

import html
import json
import logging
import os
import random
import requests
import string
import tempfile
import time

from datetime import datetime
from subprocess import call


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
        for revision in page['revisions']:
            response.append({'content': html.escape(revision['*']),
                             'pageid': page['pageid'],
                             'title': page['title']
                             })
        return response


def main():
    URL = 'http://it.wikipedia.org/'
    logger = logging.getLogger()

    # Try to read the config file with initial values.
    start_from = datetime.min
    last_id = 0
    try:
        with open('updateWikiData.conf', 'r') as conf_file:
            conf = json.loads(conf_file.read())
            start_from = datetime.strptime(conf['start_from'], '%Y%m%d%H%M%S')
            last_id = conf['last_id']
    except FileNotFoundError:
        logger.warning("No config file found. Using default values.")
    except ValueError:
        logger.warning("Corrupted config file. Using default values.")

    mediaWiki = MediaWiki(URL)

    # Initialize new config values (it must be done here as we want to store
    # the right date and time we made the request).
    new_start_from = datetime.min
    new_last_id = 0

    tmp = mediaWiki.getRecentChanges(start_from, last_id)
    print(tmp)

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

    # Write XML body.
    for item in tmp:
        print(item['revid'])
        print(item['old_revid'])

        # TODO This means that the page has been deleted or added
        # Should cover these corner cases too.
        if item['type'] != 'edit':
            continue

        revs = mediaWiki.getPageReviews([item['revid'], item['old_revid']])

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

    # TODO Here do something with what we've just produced (send to Redis) :-)

    # Cleanup temporary data.
    temp_env.cleanup()

    # Try to write config file with new values.
    with open('updateWikiData.conf', 'w') as conf_file:
        conf = {'start_from': new_start_from.strftime('%Y%m%d%H%M%S'),
                'last_id': new_last_id}
        conf_file.write(json.dumps(conf))

if __name__ == '__main__':
    main()
