#!/usr/bin/env python3
"""Join a fact stream to a small local dimension file and emit aggregates."""

from __future__ import annotations

import csv
from pathlib import Path
import sys


def load_dimensions(path: Path):
    values = {}
    with path.open("r", encoding="utf-8", newline="") as source:
        reader = csv.reader(source, delimiter="\t")
        next(reader, None)
        for fields in reader:
            if len(fields) != 2 or fields[0] in values:
                raise ValueError(f"invalid or duplicate dimension row: {fields}")
            values[fields[0]] = fields[1]
    if not values:
        raise ValueError("dimension table is empty")
    return values


def main():
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "namespaces.tsv")
    dimensions = load_dimensions(path)
    for line_number, raw_line in enumerate(sys.stdin, start=1):
        if line_number == 1 and raw_line.startswith("record_id\t"):
            continue
        fields = raw_line.rstrip("\n").split("\t", 4)
        if len(fields) != 5:
            print(f"invalid fact row at input line {line_number}", file=sys.stderr)
            raise SystemExit(1)
        _, key, words, text_bytes, _ = fields
        if key not in dimensions:
            print(f"unknown dimension key at input line {line_number}: {key}", file=sys.stderr)
            raise SystemExit(1)
        try:
            words_value = int(words)
            bytes_value = int(text_bytes)
        except ValueError:
            print(f"invalid measures at input line {line_number}", file=sys.stderr)
            raise SystemExit(1)
        print(dimensions[key], 1, words_value, bytes_value, sep="\t")


if __name__ == "__main__":
    main()
