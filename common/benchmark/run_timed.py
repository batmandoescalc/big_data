#!/usr/bin/env python3
"""Run a command and write a versioned, portable JSON timing record."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time


APPLICATION_RE = re.compile(r"application_\d+_\d+")
JOB_RE = re.compile(r"job_\d+_\d+")
COUNTER_RE = re.compile(r"^\s*([^=]+?)\s*=\s*(\d+)\s*$")
COUNTERS = {
    "CPU time spent (ms)": "cpu_time_ms",
    "Map input records": "map_input_records",
    "Map output records": "map_output_records",
    "Reduce input records": "reduce_input_records",
    "Reduce output records": "reduce_output_records",
    "HDFS: Number of bytes read": "hdfs_bytes_read",
    "HDFS: Number of bytes written": "hdfs_bytes_written",
    "FILE: Number of bytes read": "local_bytes_read",
    "FILE: Number of bytes written": "local_bytes_written",
    "Reduce shuffle bytes": "reduce_shuffle_bytes",
    "Launched map tasks": "launched_map_tasks",
    "Launched reduce tasks": "launched_reduce_tasks",
}


def parse_counters(output: str) -> dict[str, int]:
    """Return the last reported value for selected Hadoop counters."""
    counters = {}
    for line in output.splitlines():
        match = COUNTER_RE.match(line)
        if match and match.group(1).strip() in COUNTERS:
            counters[COUNTERS[match.group(1).strip()]] = int(match.group(2))
    return counters


def timed_run(
    label,
    manifest,
    command,
    *,
    engine=None,
    dataset_id=None,
    input_rows=None,
    input_bytes=None,
    output_rows=None,
):
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    completed = subprocess.run(command, text=True, encoding="utf-8", capture_output=True)
    elapsed = time.perf_counter() - started
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    print(f"TIMING {label} {elapsed:.3f} s", flush=True)
    combined = completed.stdout + "\n" + completed.stderr
    record = {
        "schema_version": 1,
        "label": label,
        "engine": engine,
        "dataset_id": dataset_id,
        "started_utc": started_utc,
        "elapsed_seconds": round(elapsed, 6),
        "exit_status": completed.returncode,
        "input_rows": input_rows,
        "input_bytes": input_bytes,
        "output_rows": output_rows,
        "application_ids": sorted(set(APPLICATION_RE.findall(combined))),
        "job_ids": sorted(set(JOB_RE.findall(combined))),
        "hadoop_counters": parse_counters(combined),
        "command": command,
    }
    manifest = Path(manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return completed.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--engine")
    parser.add_argument("--dataset-id")
    parser.add_argument("--input-rows", type=int)
    parser.add_argument("--input-bytes", type=int)
    parser.add_argument("--output-rows", type=int)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    raise SystemExit(
        timed_run(
            args.label,
            args.manifest,
            command,
            engine=args.engine,
            dataset_id=args.dataset_id,
            input_rows=args.input_rows,
            input_bytes=args.input_bytes,
            output_rows=args.output_rows,
        )
    )


if __name__ == "__main__":
    main()
