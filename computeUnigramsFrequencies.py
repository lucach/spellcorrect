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

import argparse
import codecs
import time
import multiprocessing
import Queue
import string
import sys
import re

from collections import Counter
from os import listdir
from os.path import isdir, isfile, join

exclude = set(u"\"!(),.:;?[]{}“”«»")


class Worker(multiprocessing.Process):

    def __init__(self, queue, results_queue):
        multiprocessing.Process.__init__(self)
        self._queue = queue
        self._results_queue = results_queue
        self._count = Counter()

    def _process(self, line):
        for word in line.split():
            word = ''.join(c for c in word if c not in exclude)
            search = re.compile(r'[^0-9 -/]').search
            word = word.replace(u"’", "'")
            word = word.lower()
            if bool(search(word)) and word and len(word) <= 50:
                self._count[word] += 1

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


def main():

    parser = argparse.ArgumentParser(
            description="Script to compute unigrams frequencies.")
    parser.add_argument("-f", "--file", help="source file to be processed") 
    parser.add_argument("-d", "--directory", help="directory containing a set "
                        "of files to be processed")
    parser.add_argument("-o", "--output", help="output file with results",
                        required=True)
    parser.add_argument("-v", "--verbose", help="print debugging information")

    args = parser.parse_args()

    # Make sure that one parameter has been setted.
    if args.file is None and args.directory is None:
        print("ERROR: No source specified.")
        return -1
    if args.file is not None and args.directory is not None:
        print("ERROR: Either specify a file or a directory.")
        return -1

    # Create a list with valid files ready to be processed.
    if args.file is not None:
        if isfile(args.file):
            files = [args.file]
        else:
            print("ERROR: unable to find %s." % args.file)
            return -1
    else:
        if isdir(args.directory):
            files = [f for f in listdir(args.directory)
                     if isfile(join(args.directory, f))]
            if len(files) == 0:
                print("ERROR: %s doesn't contain valid file(s)." 
                      % args.directory )
                return -1
        else:
            print("ERROR: %s is not a directory." % args.directory)
            return -1

    begin = time.time()

    workers = []
    queue = multiprocessing.JoinableQueue()
    results_queue = multiprocessing.Queue()

    # Spawn a process for every CPU.
    for _ in range(multiprocessing.cpu_count()):
        w = Worker(queue, results_queue)
        w.start()
        workers.append(w)

    for idx, filename in enumerate(files):
        print("Begin read %s." % filename)
        directory = args.directory or "."
        with codecs.open(join(directory, filename), 'r', 'utf8') as f:
            for line in f:
                queue.put(line)
        print("File %s successfully read." % filename)
        # As files can be very big, process them in batch of 10.
        if idx > 0 and idx % 10 == 0:
            queue.join()

    print("All files successfully read.")

    # Join the queue with the words to be processed. This is a synchronous 
    # call, so main() will wait for workers to complete their work.
    queue.join()

    print ("Every file has been processed. Merging...")

    # Merge the counters with the '+=' operator.
    counter = Counter()
    for _ in workers:
        counter += results_queue.get()

    # Clean process table by joining workers.
    for w in workers:
        w.join()

    print("Computing finished. Writing results...")

    with codecs.open(args.output, 'w', 'utf8') as out:
        # Write the header.
        out.write("%d %d\n" % (len(counter.values()), sum(counter.values())))

        for k, v in counter.most_common():
            out.write("%s %d\n" % (k, v))

    print("Done in %s seconds." % (time.time() - begin))

if __name__ == '__main__':
    sys.exit(main())
