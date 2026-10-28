#!/usr/bin/env python3
"""Emit per-register Flajolet-Martin maxima from JSON-line event batches."""

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
    """Read one JSON event per line and emit each local register maximum."""
    registers = int(sys.argv[1]) if len(sys.argv) > 1 else 128
    sketch = FlajoletMartin(registers)
    for line in sys.stdin:
        if line.strip():
            sketch.add(json.loads(line)["user_id"])
    for index, value in enumerate(sketch.registers):
        print(f"{index}\t{value}")


if __name__ == "__main__":
    main()
