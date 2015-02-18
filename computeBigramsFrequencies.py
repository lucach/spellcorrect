#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Spell corrector - http://www.chiodini.org/
# Copyright © 2014-2015 Luca Chiodini <luca@chiodini.org>
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
import multiprocessing
import Queue
import re
import string
import sys
import time
import traceback

from collections import Counter
from os import listdir
from os.path import isfile, join

exclude = set(u"\"!(),.:;?[]{}“”«»")


class Worker(multiprocessing.Process):

    def __init__(self, queue, results_queue):
        multiprocessing.Process.__init__(self)
        self._queue = queue
        self._results_queue = results_queue
        self._count = Counter()

    def _process(self, line):
        words = line.split()
        for word_idx in xrange(len(words) - 1):
            pair = [words[word_idx], words[word_idx + 1]]
            good = True
            for idx, word in enumerate(pair):
                word = ''.join(c for c in word if c not in exclude)
                search = re.compile(r'[^0-9 -/]').search
                word = word.replace(u"’", "'").lower()
                if not bool(search(word)) or not word or len(word) > 50:
                    good = False
                pair[idx] = word
            if good:
                self._count[" ".join(pair)] += 1

    def run(self):
        while True:
            line = None
            try:
                line = self._queue.get(timeout=0.1)
                if line is not None:
                    self._process(line)
            except Queue.Empty:
                break
            except:
                traceback.print_exc(file=sys.stdout)
            finally:
                if line is not None:
                    self._queue.task_done()
        self._results_queue.put(self._count)


if __name__ == '__main__':

    begin = time.time()
    print(begin)

    files = [f for f in listdir(sys.argv[1]) if isfile(join(sys.argv[1], f))]

    workers = []
    queue = multiprocessing.JoinableQueue()
    results_queue = multiprocessing.Queue()

    for _ in range(multiprocessing.cpu_count()):
        w = Worker(queue, results_queue)
        w.start()
        workers.append(w)

    for idx, filename in enumerate(files):
        print("Begin read " + filename)
        with codecs.open(join(sys.argv[1], filename), 'r', 'utf8') as f:
            for line in f:
                queue.put(line)
        print("File " + filename + " successfully read.")
        if idx > 0 and idx % 5 == 0:
            print("5 files read. Wait for computation...")
            queue.join()

    print "All files successfully read."

    queue.join()

    print ("All items have been processed. Merging...")

    counter = Counter()
    for _ in workers:
        counter += results_queue.get()

    for w in workers:
        w.join()

    print("Computing finished. Writing results...")

    with codecs.open(sys.argv[2], 'w', 'utf8') as out:
        out.write(str(len(counter.values())) + " " + str(sum(counter.values()))
                  + "\n")

        for k, v in counter.most_common():
            out.write(k + " " + str(v) + "\n")

    print("Done in " + str(time.time() - begin))
