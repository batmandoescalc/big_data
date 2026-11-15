#!/usr/bin/env python3
"""Add up the reducers' ``distinct<TAB>count`` lines into the final exact count."""

from __future__ import annotations

import sys


def finish(lines) -> int:
    """Return the sum of every reducer part file's count."""
    total = 0
    for line in lines:
        line = line.strip()
        if line:
            total += int(line.split("\t")[1])
    return total


def main():
    print(finish(sys.stdin))


if __name__ == "__main__":
    main()
