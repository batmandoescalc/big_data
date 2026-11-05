#!/usr/bin/env python3
"""Predict full-day run times and memory from the 2-hour timing run.

We did not time each algorithm on the full day (135 million lines): the
timing script loads every line into memory first, which would need about
30 GB.  This script scales the measured 2-hour numbers up instead:

    python3 week-08/scripts/project_full_day.py \\
        --timings week-08/results/runtimes-2-hours.json \\
        --full-day week-08/results/desktop-full-day.json \\
        --check week-08/results/runtimes-3-hours.json \\
        --output week-08/results/full-day-projection.json

Rules:
- Time grows with the number of lines: every method does a fixed amount of
  work per line.  Scale factor = full-day lines / 2-hour lines.
- Sketch memory is fixed in advance and does not grow with the data.  The
  Bloom filter is the exception: the full-day run sized it for 60 million
  keys, so its size comes from that run.
- Exact memory grows with the number of distinct pages, in the jumps Python
  uses to grow a set or dict (the table doubles or quadruples when full).
  The model below reproduces the 2-hour measurements (402.7 MB set,
  503.3 MB dict table) and is then applied to the full day's distinct pages.
- ``--check`` takes a second, larger timing run (3 hours) and records how
  much each time grew compared with the growth in lines.  Sketch times grew
  in step with lines; exact set/dict times grew faster (each resize copies
  the whole table, and bigger tables miss the CPU cache more), so the
  predicted exact times are a floor, not a best guess.
- DGIM's exact side keeps only hot lines inside the 1,000,000-line window,
  so it stays small at any data size.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def set_peak_bytes(n: int) -> int:
    """Peak table bytes while a CPython 3.12 set grows to hold n keys (resize = old + new table)."""
    size, mask, peak = 8, 7, 0
    while True:
        limit = (mask * 3) // 5 + 1  # fill level that triggers a resize
        if n < limit:
            break
        minused = limit * 2 if limit > 50000 else limit * 4
        new = 8
        while new <= minused:
            new <<= 1
        peak = max(peak, (size + new) * 16)
        size, mask = new, new - 1
    return max(peak, size * 16)


def _dict_bytes(size: int) -> int:
    usable = (size * 2) // 3
    index = 1 if size <= 0xFF else 2 if size <= 0xFFFF else 4 if size <= 0xFFFFFFFF else 8
    return size * index + usable * 24


def dict_peak_bytes(n: int) -> int:
    """Peak table bytes while a CPython 3.12 dict grows to hold n keys."""
    size, peak = 8, 0
    while (size * 2) // 3 < n:
        target = ((size * 2) // 3) * 3
        new = 8
        while new < target:
            new <<= 1
        peak = max(peak, _dict_bytes(size) + _dict_bytes(new))
        size = new
    return max(peak, _dict_bytes(size))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--timings", type=Path, required=True)
    parser.add_argument("--full-day", type=Path, required=True)
    parser.add_argument("--check", type=Path, default=None,
                        help="a larger timing run to test the line-scaling rule against")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    small = json.loads(args.timings.read_text(encoding="utf-8"))
    full = json.loads(args.full_day.read_text(encoding="utf-8"))
    algos = small["algorithms"]
    scale = full["dataset"]["lines"] / small["lines"]
    full_build_distinct = full["algorithms"]["bloom"]["keys_inserted"]
    full_distinct = full["algorithms"]["fm"]["exact"]

    exact_mb = {
        "bloom": set_peak_bytes(full_build_distinct) / 1e6,
        "fm": set_peak_bytes(full_distinct) / 1e6,
        "ams": dict_peak_bytes(full_distinct) / 1e6,
        "dgim": algos["dgim"]["exact"]["peak_traced_mb"],
    }
    sketch_mb = {
        "bloom": full["algorithms"]["bloom"]["sketch_memory_bytes"] / 1e6,
        "fm": algos["fm"]["sketch"]["peak_traced_mb"],
        "ams": algos["ams"]["sketch"]["peak_traced_mb"],
        "dgim": algos["dgim"]["sketch"]["peak_traced_mb"],
    }
    rows = {}
    for name, row in algos.items():
        rows[name] = {
            "sketch_seconds": round(row["sketch"]["seconds"] * scale, 1),
            "exact_seconds": round(row["exact"]["seconds"] * scale, 1),
            "sketch_mb": round(sketch_mb[name], 1),
            "exact_mb": round(exact_mb[name], 1),
        }
    check = None
    if args.check is not None:
        big = json.loads(args.check.read_text(encoding="utf-8"))
        n_big = big["algorithms"]["fm"]["exact"]["answer"]
        check = {
            "lines_growth": round(big["lines"] / small["lines"], 3),
            "time_growth": {name: {side: round(big["algorithms"][name][side]["seconds"]
                                               / algos[name][side]["seconds"], 2)
                                   for side in ("sketch", "exact")} for name in algos},
            "set_mb_model": round(set_peak_bytes(n_big) / 1e6, 1),
            "set_mb_measured": big["algorithms"]["fm"]["exact"]["peak_traced_mb"],
            "dict_mb_model": round(dict_peak_bytes(n_big) / 1e6, 1),
            "dict_mb_measured": big["algorithms"]["ams"]["exact"]["peak_traced_mb"],
        }
    result = {
        "from_lines": small["lines"],
        "to_lines": full["dataset"]["lines"],
        "time_scale": round(scale, 2),
        "full_day_distinct_pages": full_distinct,
        "full_day_bloom_build_distinct_pages": full_build_distinct,
        "model_check_2_hours": {
            "set_mb_model": round(set_peak_bytes(algos["fm"]["exact"]["answer"]) / 1e6, 1),
            "set_mb_measured": algos["fm"]["exact"]["peak_traced_mb"],
            "dict_mb_model": round(dict_peak_bytes(algos["fm"]["exact"]["answer"]) / 1e6, 1),
            "dict_mb_measured": algos["ams"]["exact"]["peak_traced_mb"],
        },
        "check_against_larger_run": check,
        "projected": rows,
        "note": ("Predicted, not measured. Sketch times scale with lines. Exact times are a floor: "
                 "set/dict time grew faster than lines in the 3-hour check. Memory counts only the "
                 "set/dict table, not the page names."),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
