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


# Patterns used to extract Hadoop application and job IDs from command output.
APPLICATION_RE = re.compile(r"application_\d+_\d+")
JOB_RE = re.compile(r"job_\d+_\d+")

# Matches counter lines formatted as "Counter name = integer value".
COUNTER_RE = re.compile(r"^\s*([^=]+?)\s*=\s*(\d+)\s*$")

# Map Hadoop counter names to stable, machine-readable JSON field names.
# Only these selected counters are included in the timing record.
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
    """Extract selected Hadoop counters, retaining the last reported value."""
    counters = {}

    # Process output line by line because Hadoop counters may be embedded in
    # the standard output or standard error of the executed command.
    for line in output.splitlines():
        match = COUNTER_RE.match(line)

        # Ignore lines that do not match the counter format or contain
        # counters that are not in our predefined list.
        if match and match.group(1).strip() in COUNTERS:
            counter_name = match.group(1).strip()
            counter_value = int(match.group(2))

            # Repeated counter names overwrite earlier values, so the
            # returned dictionary contains the last reported value.
            counters[COUNTERS[counter_name]] = counter_value

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
    # Record the wall-clock start time in UTC for cross-run comparisons.
    started_utc = datetime.now(timezone.utc).isoformat()

    # Use a monotonic clock to measure elapsed time accurately, avoiding
    # issues caused by system clock adjustments during command execution.
    started = time.perf_counter()

    # Run the requested command, capturing both output streams so they can
    # be displayed to the user and inspected for Hadoop metadata.
    completed = subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )

    # Measure total elapsed time, including time spent waiting for the
    # command to finish.
    elapsed = time.perf_counter() - started

    # Preserve the command's original output so the wrapper remains useful
    # for interactive execution and debugging.
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)

    # Print a concise timing summary to standard output.
    print(f"TIMING {label} {elapsed:.3f} s", flush=True)

    # Search both output streams because Hadoop IDs and counters may appear
    # in either one.
    combined = completed.stdout + "\n" + completed.stderr

    # Build a versioned JSON record containing the execution metadata,
    # optional dataset information, timing results, and Hadoop metrics.
    record = {
        # Allows future changes to the record format to be identified.
        "schema_version": 1,
        "label": label,
        "engine": engine,
        "dataset_id": dataset_id,
        "started_utc": started_utc,
        "elapsed_seconds": round(elapsed, 6),

        # Preserve the command's exit status so callers can determine
        # whether execution succeeded without parsing its output.
        "exit_status": completed.returncode,

        # Optional workload metadata supplied by the caller.
        "input_rows": input_rows,
        "input_bytes": input_bytes,
        "output_rows": output_rows,

        # Extract unique Hadoop IDs and sort them for deterministic output.
        "application_ids": sorted(set(APPLICATION_RE.findall(combined))),
        "job_ids": sorted(set(JOB_RE.findall(combined))),

        # Include only the Hadoop counters recognized by parse_counters().
        "hadoop_counters": parse_counters(combined),

        # Store the command as a list of arguments, preserving argument
        # boundaries without relying on shell-specific quoting.
        "command": command,
    }

    # Ensure the destination directory exists before writing the record.
    manifest = Path(manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    # Write human-readable JSON using UTF-8, with a trailing newline.
    manifest.write_text(
        json.dumps(record, indent=2) + "\n",
        encoding="utf-8",
    )

    # Return the original command's exit status so the wrapper can propagate
    # success or failure to the calling process.
    return completed.returncode


def main():
    # Define the command-line interface for the timing wrapper.
    parser = argparse.ArgumentParser(description=__doc__)

    # Required fields identify the run and the output JSON file.
    parser.add_argument("--label", required=True)
    parser.add_argument("--manifest", type=Path, required=True)

    # Optional metadata describes the execution engine and workload.
    parser.add_argument("--engine")
    parser.add_argument("--dataset-id")
    parser.add_argument("--input-rows", type=int)
    parser.add_argument("--input-bytes", type=int)
    parser.add_argument("--output-rows", type=int)

    # Accept all remaining arguments as the command to execute.
    # Using REMAINDER allows the wrapped command to have its own options.
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    # Treat an optional "--" as a separator between this wrapper's options
    # and the command being timed.
    command = (
        args.command[1:]
        if args.command[:1] == ["--"]
        else args.command
    )

    # Require an actual command to run; otherwise, display an argparse error.
    if not command:
        parser.error("a command is required after --")

    # Run the command and exit with its return code so scripts invoking this
    # wrapper can detect failures in the underlying command.
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


# Run the command-line entry point only when this file is executed directly,
# not when it is imported as a module.
if __name__ == "__main__":
    main()