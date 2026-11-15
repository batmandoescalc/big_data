#!/usr/bin/env python3
"""Turn merged FM registers (reducer output) into the distinct-page estimate.

Week 7's Hadoop job stopped at the merged register array.  This last step
reads ``register<TAB>rank`` lines and applies the same estimate formula as the
single-process sketch, so the two answers can be compared directly.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pageviews import HashedFM  # noqa: E402


def finish(lines, register_bits: int = 12) -> HashedFM:
    """Load reducer lines into a sketch; registers never seen stay 0."""
    sketch = HashedFM(register_bits)
    for line in lines:
        line = line.strip()
        if line:
            index, rank = line.split("\t")
            sketch.registers[int(index)] = int(rank)
    return sketch


def main():
    register_bits = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    sketch = finish(sys.stdin, register_bits)
    print(json.dumps({"registers": sketch.m,
                      "registers_touched": sketch.m - sketch.registers.count(0),
                      "estimate": sketch.estimate()}))


if __name__ == "__main__":
    main()
