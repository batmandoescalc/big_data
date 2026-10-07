#!/usr/bin/env python3
"""Compare normalized SQLite and Hadoop aggregate outputs exactly."""

import argparse
import hashlib
from pathlib import Path


def canonical(path: Path):
    lines = sorted(line.rstrip("\r\n") for line in path.read_text(encoding="utf-8").splitlines())
    data = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    return data, hashlib.sha256(data).hexdigest()


def verify(sqlite_output: Path, hadoop_output: Path):
    sqlite_data, sqlite_hash = canonical(sqlite_output)
    hadoop_data, hadoop_hash = canonical(hadoop_output)
    if sqlite_data != hadoop_data:
        raise ValueError(
            f"outputs differ: SQLite {sqlite_hash}, Hadoop {hadoop_hash}"
        )
    print(f"exact match: {sqlite_hash}")
    return sqlite_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sqlite_output", type=Path)
    parser.add_argument("hadoop_output", type=Path)
    args = parser.parse_args()
    verify(args.sqlite_output, args.hadoop_output)


if __name__ == "__main__":
    main()
