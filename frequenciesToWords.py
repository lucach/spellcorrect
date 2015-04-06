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

import argparse
import codecs
import sys


def main():

    parser = argparse.ArgumentParser(
        description="Script to get pure words from unigrams frequencies.")
    parser.add_argument("-f", "--file", help="source file to be processed",
                        required=True)
    parser.add_argument("-o", "--output", help="output file with results",
                        required=True)

    args = parser.parse_args()

    words = set()

    # Process input file and save keys.
    with codecs.open(args.file, 'r', 'utf8') as f:
        idx = 0
        for line in f:
            if idx > 0:  # skip first line (header)
                vals = line.rsplit(' ', 1)
                words.add(vals[0])
            idx += 1

    # Write keys to output file.
    with codecs.open(args.output, 'w', 'utf8') as f:
        for w in words:
            f.write("%s\n" % w)

if __name__ == '__main__':
    sys.exit(main())
