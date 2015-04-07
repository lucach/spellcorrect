#!/usr/bin/env python2

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

from __future__ import division

import codecs
import collections
import datetime
import redis
import sys

from flask import Flask
from flask.ext import restful
from google.appengine.api import memcache


app = Flask(__name__)
api = restful.Api(app)
alphabet = 'abcdefghijklmnopqrstuvwxyz'

# Read words set.
WORDS = set()
with codecs.open('words', 'r', 'utf8') as f:
    for line in f:
        WORDS.add(line.rstrip('\n'))
init_time = datetime.datetime.now()

# Redis connections.
UNIGRAMS_REDIS = redis.StrictRedis(host='chiodini.no-ip.org', port=6379, db=0)
BIGRAMS_REDIS = redis.StrictRedis(host='chiodini.no-ip.org', port=6379, db=1)


# Raw probabilities.
UNIGRAMS_SUM = 311683252
BIGRAMS_SUM = 300305000


def unigram_not_found_p():
    return 1 / UNIGRAMS_SUM


def bigram_not_found_p():
    return 1 / BIGRAMS_SUM


def edits1(word):
    splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
    deletes = [a + b[1:] for a, b in splits if b]
    transposes = [a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1]
    replaces = [a + c + b[1:] for a, b in splits for c in alphabet if b]
    inserts = [a + c + b for a, b in splits for c in alphabet]
    return set(deletes + transposes + replaces + inserts)


def known_edits2(word):
    return set(e2 for e1 in edits1(word) for e2 in edits1(e1) if e2 in WORDS)


def known(words):
    return set(w for w in words if w in WORDS)


def getvalue(word_list):
    w_prev = word_list[0]
    w = word_list[1]
    w_next = word_list[2]
    channel_model_p = word_list[3]

    try:
        prev = int(BIGRAMS_REDIS.get(w_prev + " " + w)) / BIGRAMS_SUM
    except:
        prev = bigram_not_found_p()
    try:
        cur = int(UNIGRAMS_REDIS.get(w)) / UNIGRAMS_SUM
    except:
        cur = unigram_not_found_p()
    try:
        nex = int(BIGRAMS_REDIS.get(w + " " + w_next)) / BIGRAMS_SUM
    except:
        nex = bigram_not_found_p()

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


class Corrector(restful.Resource):
    def parse(self, words_str):
        words = words_str.split()
        res = ""
        if len(words) == 1:
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

        return {'input': words_str,
                'corrected': res}

    def get(self, words_str):
        # Try to save resources and reduce response time retrieving
        # the answer from cache.
        res = memcache.get(words_str)
        if res is None:
            res = self.parse(words_str)
            res['cache'] = False
            memcache.add(words_str, res, 3600)
        else:
            res['cache'] = True

        res['init_time'] = init_time.isoformat()
        return res

api.add_resource(Corrector, '/correct/<words_str>')

if __name__ == '__main__':
    app.run(debug=True)
