#!/usr/bin/env python2
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

from __future__ import division

import codecs
import collections
import datetime
import flask_restful
import redis
import sys
import yaml

from flask import Flask

from flask_restful.utils import cors
from google.appengine.api import memcache


app = Flask(__name__)
app._static_folder = '.' 
api = flask_restful.Api(app)
# Enable CORS.
api.decorators = [cors.crossdomain(origin='*')]

alphabet = 'abcdefghijklmnopqrstuvwxyz'

# Read words set.
WORDS = set()
with codecs.open('words', 'r', 'utf8') as f:
    for line in f:
        WORDS.add(line.rstrip('\n'))
init_time = datetime.datetime.now()

# Redis connections.

# Try to read Redis's password from config.yaml. Silently ignore errors.
password = None
try:
    with open('config.yaml', 'r') as f:
        cfg = yaml.load(f)
    password = cfg['password']
except (IOError, KeyError, ValueError):
    raise

UNIGRAMS_REDIS = redis.StrictRedis(host='redis.spellcorrect.chiodini.org',
                                   port=6379, db=0, password=password)
BIGRAMS_REDIS = redis.StrictRedis(host='redis.spellcorrect.chiodini.org',
                                  port=6379, db=1, password=password)

queries = 0


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

    # TODO REMOVE Display queries for debug purposes.
    global queries
    queries = 3 * len(extended_candidates)

    # As the number of queries can be really high and we aim for efficiency,
    # a critical aspect is the number of back-and-forth TCP packets between the
    # client and the server. Redis instance can theoretically be in a different
    # server; this adds some latency to every single query (in the order of
    # tens of milliseconds) and leads to unacceptable global response times.
    # By taking advantage of Redis pipelines, all the queries are initially
    # buffered and then issued at once, dramatically increasing performances.

    unigrams_pipe = UNIGRAMS_REDIS.pipeline(transaction=False)
    bigrams_pipe = BIGRAMS_REDIS.pipeline(transaction=False)

    for candidate in extended_candidates:
        w_prev = candidate[0]
        w = candidate[1]
        w_next = candidate[2]
        channel_model_p = candidate[3]

        try:
            unigrams_pipe.get(w)
        except:
            raise

        try:
            bigrams_pipe.get(w_prev + " " + w)
        except:  # dummy value
            bigrams_pipe.get("")

        try:
            bigrams_pipe.get(w + " " + w_prev)
        except:  # dummy value
            bigrams_pipe.get("")

    # Execute pipelines in a single command.
    unigrams_values = unigrams_pipe.execute()
    bigrams_values = bigrams_pipe.execute()

    # Compute the probability for each candidate.
    for idx, candidate in enumerate(extended_candidates):
        p1 = unigrams_values[idx] or 1.0
        p2 = bigrams_values[2 * idx] or 1.0
        p3 = bigrams_values[2 * idx + 1] or 1.0
        p4 = candidate[3]
        candidate.append(int(p1) * int(p2) * int(p3) * p4)

    # Return the maximum (choosing on the fifth parameter, i.e. the
    # computed probability).
    return max(extended_candidates, key=lambda c: c[4])


class Index(flask_restful.Resource):
    def get(self):
        return app.send_static_file('index.html')

class Corrector(flask_restful.Resource):
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
        begin_time = datetime.datetime.now()
        # Try to save resources and reduce response time retrieving
        # the answer from cache.
        res = memcache.get(words_str)
        if res is None:
            res = self.parse(words_str)
            res['cache'] = False
            memcache.add(words_str, res, 86400)
        else:
            res['cache'] = True

        res['init_time'] = init_time.isoformat()
        res['queries'] = queries
        res['elapsed_time'] = str(datetime.datetime.now() - begin_time)
        return res

api.add_resource(Corrector, '/correct/<words_str>')
api.add_resource(Index, '/')

if __name__ == '__main__':
    app.run(debug=True)
