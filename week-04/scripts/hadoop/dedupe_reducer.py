#!/usr/bin/env python3
"""Collapse repeated 'id1<TAB>id2' lines; a pair found by several bands appears once.

Output is 'id1<TAB>id2<TAB>bands', where bands counts the buckets that agreed.
"""

import sys


def main():
    current, count = None, 0
    for line in sys.stdin:
        pair = line.rstrip("\n")
        if pair != current:
            if current is not None:
                print(f"{current}\t{count}")
            current, count = pair, 0
        count += 1
    if current is not None:
        print(f"{current}\t{count}")


if __name__ == "__main__":
    main()
