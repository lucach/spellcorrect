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
import requests
import tempfile

from subprocess import call


class MediaWiki:

    def __init__(self, base_URL):
        # Try to ease the interface fixing common URL mistakes.
        if not base_URL.endswith('w/api.php'):
            if not base_URL[-1] == '/':
                base_URL += '/'
            base_URL += 'w/api.php'
        self.base_URL = base_URL

    def getRecentChanges(self, start_from=0, n=3, namespace=0):
        parameters = {'action': 'query',
                      'format': 'json',
                      'list': 'recentchanges',
                      'continue': '',
                      'rclimit': n,
                      'rcnamespace': namespace,
                      'rcstart': start_from}
        r = requests.get(self.base_URL, params=parameters).json()
        return r['query']['recentchanges']

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

    mediaWiki = MediaWiki(URL)
    for item in mediaWiki.getRecentChanges(0, 1):
        print(item['revid'])
        print(item['old_revid'])
        revs = mediaWiki.getPageReviews([item['revid'], item['old_revid']])

        # Create a temporary workspace.
        with tempfile.TemporaryDirectory() as path:
            # Create XML files.

            # Old revision (if present).
            if item['old_revid'] > 0:
                with open(path + '/old.xml', 'w') as f:
                    f.write("<mediawiki>")
                    f.write("<base>" + URL + "wiki" + "</base>")
                    f.write("<page>")
                    f.write("<title>" + revs[0]['title'] + "</title>")
                    f.write("<id>" + str(revs[0]['pageid']) + "</id>")
                    f.write("<revision>")
                    f.write("<id>" + str(item['old_revid']) + "</id>")
                    f.write("<text>" + revs[0]['content'] + "</text>")
                    f.write("</revision></page></mediawiki>")

            # New revision.
            with open(path + '/new.xml', 'w') as f:
                f.write("<mediawiki>")
                f.write("<base>" + URL + "wiki" + "</base>")
                f.write("<page>")
                f.write("<title>" + revs[1]['title'] + "</title>")
                f.write("<id>" + str(revs[1]['pageid']) + "</id>")
                f.write("<revision>")
                f.write("<id>" + str(item['revid']) + "</id>")
                f.write("<text>" + revs[1]['content'] + "</text>")
                f.write("</revision></page></mediawiki>")

            # Execute WikiExtractor to clean WikiText syntax.
            # These two calls should produce old.raw and new.raw.
            # TODO Catch exceptions.

            call(["./WikiExtractorMT.py", "-fplain", "-t1",
                  "-o" + path + "/old.raw", path + "/old.xml", ""])
            call(["./WikiExtractorMT.py", "-fplain", "-t1",
                  "-o" + path + "/new.raw", path + "/new.xml", ""])

            # Execute computeFrequencies to get {old, new}.{unigrams, bigrams}
            # frequencies.
            # TODO Catch exceptions.

            call(["./computeFrequencies.py", "-tunigrams",
                  "-f" + path + "/old.raw", "-o" + path + "/old.unigrams"])
            call(["./computeFrequencies.py", "-tunigrams",
                  "-f" + path + "/new.raw", "-o" + path + "/new.unigrams"])
            call(["./computeFrequencies.py", "-tbigrams",
                  "-f" + path + "/old.raw", "-o" + path + "/old.bigrams"])
            call(["./computeFrequencies.py", "-tbigrams",
                  "-f" + path + "/new.raw", "-o" + path + "/new.bigrams"])


if __name__ == '__main__':
    main()
