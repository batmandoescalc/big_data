#!/usr/bin/env python3
"""Read transcript lines and emit one tab-separated word/count pair per word."""

import re
import sys


# English letters, optionally joined by apostrophes. Other characters separate words.
WORD = re.compile(r"[a-z]+(?:'[a-z]+)*")


def main():
    for line in sys.stdin:
        line = line.lower().replace("’", "'")
        for word in WORD.findall(line):
            print(f"{word}\t1")


if __name__ == "__main__":
    main()
