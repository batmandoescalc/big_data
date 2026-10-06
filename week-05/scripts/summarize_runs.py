#!/usr/bin/env python3
"""Summarize first and median successful runtime records without hiding cold starts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import median


def summarize(root: Path):
    groups = {}
    for path in sorted(root.rglob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if "elapsed_seconds" not in record or "engine" not in record:
            continue
        key = (record.get("dataset_id"), record.get("engine"), record.get("label"))
        groups.setdefault(key, []).append((record.get("started_utc") or "", path, record))
    rows = []
    for (dataset, engine, label), records in sorted(groups.items()):
        ordered = sorted(records)
        successful = [item for item in ordered if item[2].get("exit_status") == 0]
        elapsed = [float(item[2]["elapsed_seconds"]) for item in successful]
        first = ordered[0][2]
        rows.append(
            {
                "dataset_id": dataset,
                "engine": engine,
                "label": label,
                "attempts": len(ordered),
                "successful_attempts": len(successful),
                "first_seconds": first["elapsed_seconds"],
                "first_exit_status": first.get("exit_status"),
                "median_success_seconds": median(elapsed) if elapsed else "",
                "input_rows": first.get("input_rows"),
                "input_bytes": first.get("input_bytes"),
                "output_rows": first.get("output_rows"),
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rows = summarize(args.runtime_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]) if rows else ["dataset_id"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} summary rows to {args.output}")


if __name__ == "__main__":
    main()
