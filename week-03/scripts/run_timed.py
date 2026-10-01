#!/usr/bin/env python3
"""Run a command and write portable JSON timing evidence."""

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


def timed_run(label, manifest, command, input_rows=None, output_rows=None):
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    completed = subprocess.run(command, text=True, encoding="utf-8", capture_output=True)
    elapsed = time.perf_counter() - started
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    applications = sorted(set(APPLICATION_RE.findall(completed.stdout + completed.stderr)))
    record = {
        "label": label,
        "started_utc": started_utc,
        "elapsed_seconds": round(elapsed, 6),
        "exit_status": completed.returncode,
        "input_rows": input_rows,
        "output_rows": output_rows,
        "application_ids": applications,
        "command": command,
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return completed.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--input-rows", type=int)
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
            input_rows=args.input_rows,
            output_rows=args.output_rows,
        )
    )


if __name__ == "__main__":
    main()
