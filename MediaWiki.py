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
    """Wrap MediaWiki API in a handy class.

    """
    def __init__(self, base_URL):

        # Try to ease the interface fixing common URL mistakes.
        if not base_URL.endswith('w/api.php'):
            if not base_URL[-1] == '/':
                base_URL += '/'
            base_URL += 'w/api.php'
        self.base_URL = base_URL

    def getRecentChanges(self, start_from, last_id=0, namespace=0):
        """Return a list of objects. Each of them represents a recent change.

        start_from (datetime): minimum datetime for recent changes.
        last_id (int): minimum ID of returned objects.
        namespace (int): namespace ID where to retrieve recent change.

        return (list): a list of objects, each represents a recent change.

        """
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
        """Return a list of objects. Each of them represents a page at a
        specific revision.

        revIDs (list): a list of revision identifiers.

        return (list|None): a list of pages, one for supplied revision ID or
            None if the original list was empty.

        """
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
