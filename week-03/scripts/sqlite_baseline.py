#!/usr/bin/env python3
"""Run the Week 3 join and grouped aggregation with SQLite."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sqlite3
import time


JOIN_QUERY = """
SELECT u.utterance_id, u.mission_time, u.speaker_code, s.category,
       u.word_count, u.text
FROM utterances AS u
JOIN speakers AS s ON s.speaker_code = u.speaker_code
ORDER BY u.speaker_code, u.utterance_id
"""

AGGREGATE_QUERY = """
SELECT s.category, COUNT(*) AS utterance_count,
       SUM(u.word_count) AS total_words
FROM utterances AS u
JOIN speakers AS s ON s.speaker_code = u.speaker_code
GROUP BY s.category
ORDER BY s.category
"""


def read_tsv(path: Path):
    with path.open(encoding="utf-8", newline="") as stream:
        yield from csv.DictReader(stream, delimiter="\t")


def write_rows(path: Path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerows(rows)


def run(utterances_path: Path, speakers_path: Path, output_dir: Path):
    if output_dir.exists():
        raise ValueError(f"Output already exists: {output_dir}")
    utterances = list(read_tsv(utterances_path))
    speakers = list(read_tsv(speakers_path))
    output_dir.mkdir(parents=True)
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    started = time.perf_counter()
    with sqlite3.connect(":memory:") as database:
        database.executescript(
            """
            CREATE TABLE speakers (
                speaker_code TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                description TEXT NOT NULL
            );
            CREATE TABLE utterances (
                utterance_id TEXT PRIMARY KEY,
                mission_time TEXT NOT NULL,
                speaker_code TEXT NOT NULL,
                word_count INTEGER NOT NULL CHECK (word_count >= 0),
                text TEXT NOT NULL
            );
            """
        )
        database.executemany(
            "INSERT INTO speakers VALUES (?, ?, ?)",
            ((r["speaker_code"], r["category"], r["description"]) for r in speakers),
        )
        database.executemany(
            "INSERT INTO utterances VALUES (?, ?, ?, ?, ?)",
            (
                (
                    r["utterance_id"],
                    r["mission_time"],
                    r["speaker_code"],
                    int(r["word_count"]),
                    r["text"],
                )
                for r in utterances
            ),
        )
        joined = list(database.execute(JOIN_QUERY))
        aggregated = list(database.execute(AGGREGATE_QUERY))
    elapsed = time.perf_counter() - started
    write_rows(output_dir / "joined.tsv", joined)
    write_rows(output_dir / "aggregates.tsv", aggregated)
    metrics = {
        "tool": "sqlite",
        "started_utc": started_utc,
        "elapsed_seconds": round(elapsed, 6),
        "exit_status": 0,
        "input_rows": len(utterances) + len(speakers),
        "utterance_rows": len(utterances),
        "speaker_rows": len(speakers),
        "joined_rows": len(joined),
        "aggregate_rows": len(aggregated),
    }
    (output_dir / "runtime.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--utterances", type=Path, required=True)
    parser.add_argument("--speakers", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.utterances, args.speakers, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
