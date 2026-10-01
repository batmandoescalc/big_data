#!/usr/bin/env python3
"""Emit every candidate pair from buckets with 2+ members.

Input is sorted by bucket key, but Hadoop does not order the values within a
key, so each bucket's members are buffered and sorted before pairing.
"""

import sys

import lsh


def emit(members):
    for a, b in lsh.pairs_in_bucket(members):
        print(f"{a}\t{b}")


def main():
    current, members = None, []
    for line in sys.stdin:
        key, window_id = line.rstrip("\n").split("\t")
        if key != current:
            emit(members)
            current, members = key, []
        members.append(window_id)
    emit(members)  # the last bucket has no following key to trigger it


if __name__ == "__main__":
    main()
