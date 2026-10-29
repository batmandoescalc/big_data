#!/usr/bin/env python3
"""Compute FM trailing-zero observations for one Hadoop input partition."""

from __future__ import annotations

import json
from pathlib import Path
import sys

# Hadoop Streaming puts each file in the task working directory.  Keep that
# directory first, then retain the source-tree path for local unit tests.
sys.path.insert(0, ".")
sys.path.insert(1, str(Path(__file__).resolve().parents[1]))
from streaming import FlajoletMartin  # noqa: E402


def main():
    """Hash each user, count trailing zeros, and emit local register maxima.

    ``FlajoletMartin.add`` performs the hash and trailing-zero calculation for
    every register.  This mapper keeps the largest observation it sees in its
    own input partition.  The reducer does not repeat that calculation; it
    only merges these already-computed mapper maxima.
    """
    registers = int(sys.argv[1]) if len(sys.argv) > 1 else 128
    sketch = FlajoletMartin(registers)
    for line in sys.stdin:
        if line.strip():
            # add() hashes this user independently for each register, counts
            # the trailing zero bits, and retains each partition-local max.
            sketch.add(json.loads(line)["user_id"])
    # Emit one compact summary record per register, not one record per event.
    for index, value in enumerate(sketch.registers):
        print(f"{index}\t{value}")


if __name__ == "__main__":
    main()
