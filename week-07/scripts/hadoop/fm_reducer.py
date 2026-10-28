#!/usr/bin/env python3
"""Merge mapper register maxima and emit one distributed FM summary."""

from __future__ import annotations

import sys


def main():
    """Hadoop groups values by register; retain its maximum as the merge rule."""
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
