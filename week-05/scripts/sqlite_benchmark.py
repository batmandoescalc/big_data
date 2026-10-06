#!/usr/bin/env python3
"""Load generic facts and dimensions into SQLite and aggregate by category."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sqlite3
import sys


QUERY = """
SELECT d.category, COUNT(*), SUM(f.word_count), SUM(f.text_bytes)
FROM facts AS f
JOIN dimensions AS d ON d.dimension_key = f.dimension_key
GROUP BY d.category
ORDER BY d.category
"""

# Real Wikipedia pages can exceed csv's conservative 128 KiB default field
# limit. The TSV is produced by our own sanitizer, so permit platform-sized
# text fields while retaining the exact five-column validation below.
field_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(field_limit)
        break
    except OverflowError:
        field_limit //= 10


def rows(path, expected_fields):
    with path.open("r", encoding="utf-8", newline="") as source:
        reader = csv.reader(source, delimiter="\t")
        next(reader, None)
        for line_number, fields in enumerate(reader, start=2):
            if len(fields) != expected_fields:
                raise ValueError(f"{path}:{line_number}: expected {expected_fields} fields")
            yield fields


def run(facts: Path, dimensions: Path, database: Path, output: Path):
    if database.exists() or output.exists():
        raise FileExistsError("SQLite database and output paths must be new")
    database.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            PRAGMA journal_mode=OFF;
            PRAGMA synchronous=OFF;
            CREATE TABLE dimensions (
                dimension_key TEXT PRIMARY KEY,
                category TEXT NOT NULL
            );
            CREATE TABLE facts (
                record_id TEXT PRIMARY KEY,
                dimension_key TEXT NOT NULL,
                word_count INTEGER NOT NULL,
                text_bytes INTEGER NOT NULL,
                text TEXT NOT NULL
            );
            """
        )
        connection.executemany("INSERT INTO dimensions VALUES (?, ?)", rows(dimensions, 2))
        batch = []
        loaded = 0
        for record_id, key, words, text_bytes, text in rows(facts, 5):
            batch.append((record_id, key, int(words), int(text_bytes), text))
            if len(batch) >= 5000:
                connection.executemany("INSERT INTO facts VALUES (?, ?, ?, ?, ?)", batch)
                loaded += len(batch)
                batch.clear()
        if batch:
            connection.executemany("INSERT INTO facts VALUES (?, ?, ?, ?, ?)", batch)
            loaded += len(batch)
        connection.execute("CREATE INDEX facts_dimension_idx ON facts(dimension_key)")
        results = list(connection.execute(QUERY))
        connection.commit()
    finally:
        connection.close()
    with output.open("w", encoding="utf-8", newline="") as target:
        for category, count, words, text_bytes in results:
            target.write(f"{category}\t{count}\t{words}\t{text_bytes}\n")
    summary = {"input_rows": loaded, "output_rows": len(results)}
    print(json.dumps(summary, sort_keys=True))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("facts", type=Path)
    parser.add_argument("dimensions", type=Path)
    parser.add_argument("database", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.facts, args.dimensions, args.database, args.output)


if __name__ == "__main__":
    main()
