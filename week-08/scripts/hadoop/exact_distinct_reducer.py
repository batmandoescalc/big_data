#!/usr/bin/env python3
"""Hadoop Streaming reducer: count the distinct keys in sorted input."""

from __future__ import annotations

import sys


def main():
    """Count how many times the key changes, then print ``distinct<TAB>count``.

    Hadoop sorts the mapper output, so equal keys arrive together and one
    remembered key is enough: no set, no hashing.  Hadoop also sends every
    copy of a key to the same reducer, so with several reducers each prints
    the count for its own share of the keys and the counts add up.
    """
    distinct = 0
    previous = None
    for line in sys.stdin.buffer:
        key = line.split(b"\t", 1)[0].rstrip(b"\r\n")
        if key and key != previous:
            distinct += 1
            previous = key
    print(f"distinct\t{distinct}")


if __name__ == "__main__":
    main()
