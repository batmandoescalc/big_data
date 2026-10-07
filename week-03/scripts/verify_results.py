#!/usr/bin/env python3
"""Compare SQLite and Hadoop outputs after canonical line sorting."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def canonical(path: Path):
    lines = sorted(path.read_text(encoding="utf-8").splitlines())
    data = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    return lines, hashlib.sha256(data).hexdigest()


def verify(sqlite_dir: Path, hadoop_dir: Path):
    report = {"status": "match", "files": {}}
    for name in ("joined.tsv", "aggregates.tsv"):
        sql_lines, sql_hash = canonical(sqlite_dir / name)
        hadoop_lines, hadoop_hash = canonical(hadoop_dir / name)
        matches = sql_lines == hadoop_lines
        report["files"][name] = {
            "matches": matches,
            "sqlite_rows": len(sql_lines),
            "hadoop_rows": len(hadoop_lines),
            "canonical_sha256": sql_hash if matches else None,
            "sqlite_sha256": sql_hash,
            "hadoop_sha256": hadoop_hash,
        }
        if not matches:
            report["status"] = "mismatch"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-dir", type=Path, required=True)
    parser.add_argument("--hadoop-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(args.sqlite_dir, args.hadoop_dir)
    rendered = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    raise SystemExit(0 if report["status"] == "match" else 1)


if __name__ == "__main__":
    main()
