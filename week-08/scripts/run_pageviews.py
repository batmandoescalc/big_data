#!/usr/bin/env python3
"""Run Bloom, FM, AMS and DGIM over Wikipedia pageview dumps and compare to exact answers.

Usage:
    python3 week-08/scripts/run_pageviews.py --input-dir data/week-08/pageviews \\
        --hours 00-23 --output data/week-08/results/full-day.json

The last selected hour is the Bloom probe hour; earlier hours build the
filter.  Exact answers use temporary partition files (about 16 bytes per
line, 2.2 GB for the full day) under --work-dir, removed when the run ends.

On a machine without that much disk (the class head node), run only the
sketches and take the exact answers from an earlier full run on the same
files.  The sketch seeds are fixed, so the estimates match number for number:
    python3 week-08/scripts/run_pageviews.py --input-dir DIR --hours 00-23 \
        --skip-exact --exact-from full-day.json --output cluster-day.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import resource
import shutil
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from download_pageviews import parse_hours  # noqa: E402
from pageviews import fill_exact_from, find_files, run  # noqa: E402


def main(argv=None) -> int:
    """Parse arguments, run the comparison, and write the JSON report."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--hours", default="00-23", help="e.g. 00-23, 12, or 20-23")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=None,
                        help="folder for temporary exact-answer partitions (default: system temp)")
    parser.add_argument("--skip-exact", action="store_true",
                        help="run only the sketches: no temporary files, exact fields null")
    parser.add_argument("--exact-from", type=Path, default=None,
                        help="with --skip-exact: copy exact answers from an earlier full run "
                             "on the same files (refuses if the dataset differs)")
    parser.add_argument("--bloom-capacity", type=int, default=60_000_000,
                        help="keys the Bloom filter is sized for (a full day of build hours "
                             "on 2026-10-27 inserts about 48 million)")
    parser.add_argument("--bloom-fp", type=float, default=0.01)
    parser.add_argument("--fm-register-bits", type=int, default=12)
    parser.add_argument("--ams-variables", type=int, default=4096)
    parser.add_argument("--ams-groups", type=int, default=8)
    parser.add_argument("--ams-seed", type=int, default=4099)
    parser.add_argument("--hot-threshold", type=int, default=100)
    parser.add_argument("--dgim-window", type=int, default=1_000_000)
    args = parser.parse_args(argv)

    if args.exact_from is not None and not args.skip_exact:
        parser.error("--exact-from needs --skip-exact")
    reference = None
    if args.exact_from is not None:
        reference = json.loads(args.exact_from.read_text(encoding="utf-8"))
    files = find_files(args.input_dir, set(parse_hours(args.hours)))
    started = time.perf_counter()
    work_dir = None
    if args.work_dir is not None and not args.skip_exact:
        args.work_dir.mkdir(parents=True, exist_ok=True)
        work_dir = tempfile.mkdtemp(prefix="pageviews-exact-", dir=args.work_dir)
    try:
        result = run(files, bloom_capacity=args.bloom_capacity, bloom_fp=args.bloom_fp,
                     fm_register_bits=args.fm_register_bits,
                     ams_variables=args.ams_variables, ams_groups=args.ams_groups,
                     ams_seed=args.ams_seed, hot_threshold=args.hot_threshold,
                     dgim_window=args.dgim_window, work_dir=work_dir,
                     skip_exact=args.skip_exact,
                     progress=lambda message: print(message, file=sys.stderr, flush=True))
    finally:
        if work_dir is not None:
            shutil.rmtree(work_dir, ignore_errors=True)
    if reference is not None:
        try:
            fill_exact_from(result, reference)
        except ValueError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        result["exact_from_file"] = str(args.exact_from)
    result["runtime_seconds"]["wall_clock"] = round(time.perf_counter() - started, 2)
    result["resources"] = {
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "python": platform.python_version(),
        "machine": f"{platform.system()} {platform.release()} {platform.machine()}",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    summary = {name: {key: algo[key] for key in ("estimate", "exact", "error_pct")}
               for name, algo in result["algorithms"].items()}
    print(json.dumps({"dataset_lines": result["dataset"]["lines"], "summary": summary,
                      "runtime_seconds": result["runtime_seconds"],
                      "resources": result["resources"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
