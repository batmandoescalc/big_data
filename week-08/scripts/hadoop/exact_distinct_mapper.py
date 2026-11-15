#!/usr/bin/env python3
"""Hadoop Streaming mapper: one key hash per valid pageview line (exact count)."""

from __future__ import annotations

from pathlib import Path
import sys

# Hadoop Streaming ships pageviews.py into the task's working directory.
# Keep that first, then the source tree for local tests.
sys.path.insert(0, ".")
sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
from pageviews import key_hash, parse_line  # noqa: E402


def main():
    """Print the 64-bit key hash of every valid line as 16 hex digits.

    This is the exact side of the FM comparison.  The FM mapper sends at most
    4,096 register lines per input file; this mapper sends every line, so
    every page key goes through the shuffle.  The hash is the same one the
    sketches use.  The fixed width makes Hadoop's text sort put equal keys
    next to each other, which is all the reducer needs.
    """
    out = sys.stdout
    for line in sys.stdin.buffer:
        parsed = parse_line(line.rstrip(b"\r\n"))
        if parsed is not None:
            out.write(f"{key_hash(parsed[0]):016x}\n")


if __name__ == "__main__":
    main()
