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
import redis
import sys

from os.path import join


if __name__ == '__main__':

    r = redis.StrictRedis(host=sys.argv[2], port=6379, db=sys.argv[3])
    
    with codecs.open(join('.', sys.argv[1]), 'r', 'utf8') as f:
        pipe = r.pipeline() 
        linecounter = 0   
        for line in f:
            if linecounter > 0: # skip first line
                vals = line.rsplit(' ', 1)
                pipe.set(vals[0], vals[1])
                # Save every 10K keys.
                if linecounter > 0 and linecounter % 10000 == 0:
                    res = pipe.execute()
                    if (False in res):
                        print("An error occurred during saving process!")
                    else:
                        print("Save %d keys!" % linecounter)
            linecounter += 1
        pipe.execute()
        try:
            r.save()
        except:
            # save() fails if a concurrent, redis-initiated saving process is
            # in progress.
            pass