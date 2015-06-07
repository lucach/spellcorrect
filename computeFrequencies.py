#!/usr/bin/env python3
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
import logging
import multiprocessing
import queue
import re
import string
import sys
import time
import traceback

from collections import Counter
from os import listdir
from os.path import isdir, isfile, join

exclude = set(u'"!(),.:;?[]{}“”«»')


class Worker(multiprocessing.Process):
    """Class that represents a process.

    """

    def __init__(self, queue, results_queue, type):
        """Initialize the process with information it requires.

        queue (multiprocessing.JoinableQueue): the queue containing the work,
            each element is a line to be processed.
        results_queue (multiprocessing.Queue): the queue that will contain the
            results, each element is a Counter (collections.Counter).
        type (string): whether to compute 'unigrams' or 'bigrams' frequencies.

        """
        multiprocessing.Process.__init__(self)
        self._queue = queue
        self._results_queue = results_queue
        self._count = Counter()

        if type == "unigrams":
            self._process = self._processUnigrams
        elif type == "bigrams":
            self._process = self._processBigrams
        else:
            # It should never hit this, provided that the assertions before
            # work as expected.
            raise Exception("Internal error.")

    def _processUnigrams(self, line):
        """Process a line and increment Counter for each word found.

        Note: words longer than 50 chars are ignored.

        line (string): the line to be processed.

        """
        for word in line.split():
            word = ''.join(c for c in word if c not in exclude)
            search = re.compile(r'[^0-9 -/]').search
            word = word.replace(u"’", "'")
            word = word.lower()
            if bool(search(word)) and word and len(word) <= 50:
                self._count[word] += 1

    def _processBigrams(self, line):
        """Process a line and increment Counter for each pair of word found.

        It is important to define what "a pair of word" is. To simplify, we
        refer to its meaning as "two words separated by a space".

        Note: words longer than 50 chars are ignored.

        line (string): the line to be processed.

        """
        words = line.split()
        for word_idx in range(len(words) - 1):
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
        """Loop until there are (in queue) new jobs to be executed.
        At the end, put the results Counter in the appropriate queue.

        """
        while True:
            line = None
            try:
                line = self._queue.get(timeout=0.1)
                if line is not None:
                    self._process(line)
            except queue.Empty:
                break
            except:
                traceback.print_exc(file=sys.stdout)
            finally:
                if line is not None:
                    self._queue.task_done()
        self._results_queue.put(self._count)


def main():
    """Launch the script that computes frequencies.

    - Read the file (or all files within a directory) and put each line in
      queue
    - Spawn multiple processes (Worker)
    - Collect results from processes, merge them and write the results in a
      file.

    """
    parser = argparse.ArgumentParser(
        description="Script to compute unigrams and/or bigrams frequencies.")
    parser.add_argument("-f", "--file", help="source file to be processed")
    parser.add_argument("-d", "--directory", help="directory containing a set "
                        "of files to be processed")
    parser.add_argument("-t", "--type", help="whether computing 'unigrams' or "
                        "'bigrams'", required=True)
    parser.add_argument("-o", "--output", help="output file with results",
                        required=True)
    parser.add_argument("-v", "--verbose", action='store_true',
                        help="print debugging information")

    args = parser.parse_args()

    # Adjust logger verbosity.
    if args.verbose is True:
        logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s %(levelname)-8s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
    else:
        logging.basicConfig(level=logging.WARNING,
                            format='%(asctime)s %(levelname)-8s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

    logger = logging.getLogger()

    # Make sure that one parameter has been setted.
    if args.file is None and args.directory is None:
        logger.critical("No source specified.")
        return -1
    if args.file is not None and args.directory is not None:
        logger.critical("Either specify a file or a directory.")
        return -1

    # Validate the type of computation requested.
    if not (args.type == "unigrams" or args.type == "bigrams"):
        logger.critical("Wrong type: please specify 'unigrams' or 'bigrams'")
        return -1

    # Create a list with valid files ready to be processed.
    if args.file is not None:
        if isfile(args.file):
            files = [args.file]
        else:
            logger.critical("Unable to find %s." % args.file)
            return -1
    else:
        if isdir(args.directory):
            files = [f for f in listdir(args.directory)
                     if isfile(join(args.directory, f))]
            if len(files) == 0:
                logger.critical("%s doesn't contain valid file(s)."
                                % args.directory)
                return -1
        else:
            logger.critical("%s is not a directory." % args.directory)
            return -1

    begin_time = time.time()

    workers = []
    # Limit queue size to 100k items (this is due to the fact that reading
    # can be way more fast than computing; RAM is filled up abnormally).
    queue = multiprocessing.JoinableQueue(100000)
    results_queue = multiprocessing.Queue()

    # Spawn a process for every CPU.
    for _ in range(multiprocessing.cpu_count()):
        w = Worker(queue, results_queue, args.type)
        w.start()
        workers.append(w)

    for idx, filename in enumerate(files):
        logger.debug("Begin read %s." % filename)
        directory = args.directory or "."
        with codecs.open(join(directory, filename), 'r', 'utf8') as f:
            for line in f:
                queue.put(line)
        logger.debug("File %s successfully read." % filename)

    logger.debug("All files successfully read.")

    # Join the queue with the words to be processed. This is a synchronous
    # call, so main() will wait for workers to complete their work.
    queue.join()

    logger.debug("Every file has been processed. Merging...")

    # Merge the counters with the '+=' operator.
    counter = Counter()
    for _ in workers:
        counter += results_queue.get()

    # Clean process table by joining workers.
    for w in workers:
        w.join()

    logger.debug("Computing finished. Writing results...")

    with codecs.open(args.output, 'w', 'utf8') as out:
        # Write the header.
        out.write("%d %d\n" % (len(counter.values()), sum(counter.values())))

        # For each element, write the key and its value (space separated).
        for k, v in counter.most_common():
            out.write("%s %d\n" % (k, v))

    logger.debug("Done in %s seconds." % (time.time() - begin_time))

if __name__ == '__main__':
    sys.exit(main())
