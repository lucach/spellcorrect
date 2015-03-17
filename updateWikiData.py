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
        # Return None for an empty list
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
            response.append({'content:': html.escape(revision['*']),
                             'pageid': page['pageid'],
                             'title': page['title']
                             })
        return response


def main():
    mediaWiki = MediaWiki('http://it.wikipedia.org/')
    for item in mediaWiki.getRecentChanges(0, 1):
        print(item['revid'])
        print(item['old_revid'])
        resp = mediaWiki.getPageXMLByRevID([item['revid'], item['old_revid']])

        for rev in resp:
            print(rev)

if __name__ == '__main__':
    main()
