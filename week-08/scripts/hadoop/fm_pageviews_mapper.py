#!/usr/bin/env python3
"""Hadoop Streaming mapper: FM registers for one partition of pageview lines."""

from __future__ import annotations

from pathlib import Path
import sys

# Hadoop Streaming ships pageviews.py and streaming.py into the task's working
# directory.  Keep that first, then the source tree for local tests.
sys.path.insert(0, ".")
sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
from pageviews import HashedFM, key_hash, parse_line  # noqa: E402


def main():
    """Hash each "wiki title" key once and print this partition's registers.

    The mapper does all hashing.  It prints one ``register<TAB>rank`` line per
    register that was touched, so a whole hour of pageviews (about 6 million
    lines) shrinks to at most 4,096 short lines before the shuffle.
    """
    register_bits = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    sketch = HashedFM(register_bits)
    for line in sys.stdin.buffer:
        parsed = parse_line(line.rstrip(b"\r\n"))
        if parsed is not None:
            sketch.add_hash(key_hash(parsed[0]))
    out = sys.stdout
    for index, rank in enumerate(sketch.registers):
        if rank:
            out.write(f"{index}\t{rank}\n")


if __name__ == "__main__":
    main()
