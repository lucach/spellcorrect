#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Spell corrector - http://www.chiodini.org/
# Copyright © 2014-2015 Luca Chiodini <luca@chiodini.org>
#
# The algorithm for spelling correction is taken from
# http://norvig.com/spell-correct.html
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

from __future__ import division

import codecs
import collections
import redis
import sys

from werkzeug.wrappers import Request, Response
from werkzeug.routing import Map, Rule

WORDS_REDIS = redis.StrictRedis(host='127.0.0.1', port=6379, db=0)
BIGRAMS_REDIS = redis.StrictRedis(host='127.0.0.1', port=6379, db=1)
alphabet = 'abcdefghijklmnopqrstuvwxyz'

WORDS_SUM = 303784681
BIGRAMS_SUM = 148098215
WORD_NOT_FOUND_P = 1 / WORDS_SUM
BIGRAM_NOT_FOUND_P = 1 / BIGRAMS_SUM

NWORDS = set(WORDS_REDIS.keys())


def edits1(word):
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    deletes = [a + b[1:] for a, b in splits if b]
    transposes = [a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1]
    replaces = [a + c + b[1:] for a, b in splits for c in alphabet if b]
    inserts = [a + c + b for a, b in splits for c in alphabet]
    return set(deletes + transposes + replaces + inserts)


def known_edits2(word):
    return set(e2 for e1 in edits1(word) for e2 in edits1(e1) if e2 in NWORDS)


def known(words):
    return set(w for w in words if w in NWORDS)


def getvalue(word_list):
    w_prev = word_list[0]
    w = word_list[1]
    w_next = word_list[2]
    channel_model_p = word_list[3]

    try:
        prev = int(BIGRAMS_REDIS.get(w_prev + " " + w)) / BIGRAMS_SUM
    except:
        prev = BIGRAM_NOT_FOUND_P
    try:
        cur = int(WORDS_REDIS.get(w)) / WORDS_SUM
    except:
        cur = WORD_NOT_FOUND_P
    try:
        nex = int(BIGRAMS_REDIS.get(w + " " + w_next)) / BIGRAMS_SUM
    except:
        nex = BIGRAM_NOT_FOUND_P

    # Watch for floating point underflow!
    return prev * cur * nex * channel_model_p


def correct(word_prev, word, word_next):
    candidates = []

    # Add the word itself with 1.0 prob
    candidates.append([known([word]) | set([word]), 1.0])

    # Add known words within edit distance 1 with 10^-3 prob
    candidates.append([known(edits1(word)), .001])

    # Add known words within edit distance 2 with 10^-4 prob
    candidates.append([known_edits2(word), .0001])

    extended_candidates = []

    for c_set in candidates:
        current_set = set()
        probability = 1.0
        for idx, item in enumerate(c_set):
            if idx == 0:
                current_set = item
            elif idx == 1:
                probability = item

        extended_candidates.extend(
            [[word_prev, candidate, word_next, probability]
                for candidate in current_set])

    return max(extended_candidates, key=getvalue)


class web_correct(object):
    def __init__(self):
        self.url_map = Map([
            Rule('/<string:query>', endpoint='web_correct')
        ])

    def dispatch_request(self, request):
        adapter = self.url_map.bind_to_environ(request.environ)
        try:
            endpoint, values = adapter.match()
        except:
            return Response("Bad or empty request")
        query = values['query']
        words = query.split()
        res = ""
        if len(words) == 0:
            res = "Empty request"
        elif len(words) == 1:
            res = correct(None, words[0], None)[1]
        else:
            print words
            for idx in range(len(words)):
                if idx < 1:
                    words[idx] = correct(None, words[idx], words[idx + 1])[1]
                elif idx < len(words) - 1:
                    words[idx] = correct(words[idx - 1], words[idx],
                                         words[idx + 1])[1]
                else:
                    words[idx] = correct(words[idx - 1], words[idx], None)[1]
            str = ""
            for idx in range(len(words)):
                str += words[idx] + " "
            res = str[:-1]
        return Response(res)

    def wsgi_app(self, environ, start_response):
        request = Request(environ)
        response = self.dispatch_request(request)
        return response(environ, start_response)

    def __call__(self, environ, start_response):
        return self.wsgi_app(environ, start_response)

if __name__ == '__main__':
    app = web_correct()
    from werkzeug.serving import run_simple
    run_simple('0.0.0.0', 80, app, use_debugger=True, use_reloader=True)
