#!/usr/bin/env python3
"""Run the streaming mapper/reducer locally, including Hadoop's sort boundary."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def run(facts: Path, dimensions: Path, output: Path) -> int:
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    script_dir = Path(__file__).resolve().parent / "mapreduce"
    with facts.open("r", encoding="utf-8", newline="") as source:
        mapped = subprocess.run(
            [sys.executable, str(script_dir / "map_join_aggregate.py"), str(dimensions)],
            stdin=source,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        ).stdout
    shuffled = "\n".join(sorted(mapped.splitlines())) + "\n"
    reduced = subprocess.run(
        [sys.executable, str(script_dir / "aggregate_reducer.py")],
        input=shuffled,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    ).stdout
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(reduced, encoding="utf-8")
    return sum(1 for line in reduced.splitlines() if line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("facts", type=Path)
    parser.add_argument("dimensions", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(f"output_rows={run(args.facts, args.dimensions, args.output)}")


if __name__ == "__main__":
    main()
