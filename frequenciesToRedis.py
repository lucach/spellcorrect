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
import logging
import redis
import sys


def main():

    parser = argparse.ArgumentParser(
        description="Script to send frequencies to a redis database.")
    parser.add_argument("-f", "--file", help="source file with frequencies",
                        required=True)
    parser.add_argument("--host", help="redis host (default localhost)",
                        default="127.0.0.1")
    parser.add_argument("--port", help="redis port (default 6379)",
                        default=6379, type=int)
    parser.add_argument("--db", help="redis database (default 0)", default=0,
                        type=int)
    parser.add_argument("--min", help="do not send keys with value less than" +
                        " MIN", default=0, type=int)
    parser.add_argument("-v", "--verbose", action='store_true',
                        help="print debugging information")

    args = parser.parse_args()
    logger = logging.getLogger()

    # Adjust logger verbosity.
    if args.verbose is True:
        logging.basicConfig(level=logging.DEBUG,
                            format='%(asctime)s %(levelname)-8s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
    else:
        logging.basicConfig(level=logging.WARNING,
                            format='%(asctime)s %(levelname)-8s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')

    # Unfortunately we cannot catch exceptions here as redis's library uses a
    # custom connection pool and just assumes that the database is alive and
    # reachable.
    r = redis.StrictRedis(host=args.host, port=args.port, db=args.db)

    print(args.min)

    linecounter = 0
    with codecs.open(args.file, 'r', 'utf8') as f:
        pipe = r.pipeline()
        for line in f:
            if linecounter > 0:  # skip first line
                vals = line.rsplit(' ', 1)
                if (int(vals[1]) < args.min):
                    continue
                pipe.set(vals[0], vals[1])
                # Force redis to save every 10K keys.
                if linecounter > 0 and linecounter % 10000 == 0:
                    res = pipe.execute()
                    if (False in res):
                        logger.error("An error occured during saving process.")
                    else:
                        logger.debug("Saved %d keys" % linecounter)
            linecounter += 1
        pipe.execute()

    # Try to force a final save.
    try:
        r.save()
    except:
        # save() fails if a concurrent, redis-initiated saving process is
        # already in progress. So we should not worry too much, everything will
        # be good in a few seconds.
        pass

    logger.debug("Successfully done (%d keys sent)." % (linecounter - 1))

if __name__ == '__main__':
    sys.exit(main())
