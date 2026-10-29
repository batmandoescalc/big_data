#!/usr/bin/env python3
"""Merge mapper-computed FM registers; no hashing happens in this reducer."""

from __future__ import annotations

import sys


def main():
    """For each register, retain the maximum reported by any mapper.

    The mapper has already hashed every user and counted trailing zeros.  FM's
    distributed merge rule is simply ``max`` for the same register across
    partitions, so this reducer never needs the original user IDs.
    """
    current, maximum = None, None
    for line in sys.stdin:
        register, value = line.rstrip("\n").split("\t", 1)
        if current is not None and register != current:
            print(f"{current}\t{maximum}")
            maximum = None
        current = register
        maximum = max(maximum, int(value)) if maximum is not None else int(value)
    if current is not None:
        print(f"{current}\t{maximum}")


if __name__ == "__main__":
    main()
