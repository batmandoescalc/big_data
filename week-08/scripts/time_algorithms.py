#!/usr/bin/env python3
"""Time each sketch against its exact answer, one algorithm at a time.

The full-day run streams all four sketches in one pass, so it has only one
combined time.  This script answers "how long does each algorithm take, and
how long does the exact answer take?" on a smaller slice:

    python3 week-08/scripts/time_algorithms.py --input-dir data/week-08/pageviews \\
        --hours 22-23 --output week-08/results/runtimes-2-hours.json

Steps:
1. Read and parse the gzip files once, hashing each key (shared cost, timed
   on its own so it does not count against any algorithm).
2. For each algorithm, time the sketch alone and the exact method alone over
   the same in-memory stream, and record peak traced memory of each.

Exact methods are what a plain Python program would do: a ``set`` of keys
(Bloom, FM), a ``dict`` of counts (AMS), and a list of hot-line positions
(DGIM).  ``set`` and ``dict`` run in C, while the sketches are pure Python.
"""

from __future__ import annotations

import argparse
from collections import deque
import gc
import gzip
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dgim_reduced_error import DGIMReduced  # noqa: E402
from download_pageviews import parse_hours  # noqa: E402
from pageviews import HashedBloom, HashedFM, WeightedAMS, find_files, percent_error  # noqa: E402


def load(files):
    """Return per-hour lists of (key, views, hash) and the time it took."""
    started = time.perf_counter()
    hours = []
    blake, from_bytes = hashlib.blake2b, int.from_bytes
    for hour, path in sorted(files):
        keys, views, hashes = [], [], []
        with gzip.open(path, "rb") as handle:
            for line in handle:
                pieces = line.rsplit(b" ", 2)
                if len(pieces) != 3 or not pieces[1].isdigit() or b" " not in pieces[0]:
                    continue
                keys.append(pieces[0])
                views.append(int(pieces[1]))
                hashes.append(from_bytes(blake(pieces[0], digest_size=8).digest(), "little"))
        hours.append((hour, keys, views, hashes))
    return hours, time.perf_counter() - started


def timed(fn, trace_memory):
    """Run ``fn`` and return (result, seconds, peak_mb); memory is traced only on request."""
    gc.collect()
    if trace_memory:
        tracemalloc.start()
    started = time.perf_counter()
    result = fn()
    seconds = time.perf_counter() - started
    peak = None
    if trace_memory:
        peak = tracemalloc.get_traced_memory()[1] / 1e6
        tracemalloc.stop()
    return result, seconds, peak


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--hours", default="22-23")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hot-threshold", type=int, default=100)
    parser.add_argument("--dgim-window", type=int, default=1_000_000)
    parser.add_argument("--repeats", type=int, default=3,
                        help="timing runs per method; the fastest is reported")
    args = parser.parse_args(argv)

    files = find_files(args.input_dir, set(parse_hours(args.hours)))
    if len(files) < 2:
        parser.error("need at least 2 hours: earlier hours build the Bloom filter, the last probes it")
    hours, load_seconds = load(files)
    build, probe = hours[:-1], hours[-1]
    all_keys = [k for _, keys, _, _ in hours for k in keys]
    all_views = [v for _, _, views, _ in hours for v in views]
    all_hashes = [h for _, _, _, hashes in hours for h in hashes]
    build_keys = [k for _, keys, _, _ in build for k in keys]
    build_hashes = [h for _, _, _, hashes in build for h in hashes]
    _, probe_keys, _, probe_hashes = probe
    distinct_build = len(set(build_keys))

    def bloom_sketch():
        bloom = HashedBloom.for_capacity(distinct_build, 0.01)
        for h in build_hashes:
            bloom.add_hash(h)
        return sum(1 for h in probe_hashes if bloom.contains_hash(h))

    def bloom_exact():
        seen = set(build_keys)
        return sum(1 for k in probe_keys if k in seen)

    def fm_sketch():
        fm = HashedFM(12)
        for h in all_hashes:
            fm.add_hash(h)
        return fm.estimate()

    def fm_exact():
        return len(set(all_keys))

    def ams_sketch():
        ams = WeightedAMS(4096, 4099, 8)
        for h, c in zip(all_hashes, all_views):
            ams.add(h, c)
        return ams.estimate()

    def ams_exact():
        counts = {}
        for k, c in zip(all_keys, all_views):
            counts[k] = counts.get(k, 0) + c
        return sum(c * c for c in counts.values())

    threshold, window = args.hot_threshold, args.dgim_window

    def dgim_sketch():
        dgim = DGIMReduced(window, r=2)
        t = 0
        for c in all_views:
            t += 1
            if c >= threshold:
                dgim.add_zeros(t - 1 - dgim.time)
                dgim.add(1)
        dgim.add_zeros(t - dgim.time)
        return dgim.estimate(window)

    def dgim_exact():
        hot = deque()
        t = 0
        for c in all_views:
            t += 1
            if c >= threshold:
                hot.append(t)
                while hot[0] <= t - window:
                    hot.popleft()
        return sum(1 for x in hot if x > t - window)

    methods = {"bloom": (bloom_sketch, bloom_exact), "fm": (fm_sketch, fm_exact),
               "ams": (ams_sketch, ams_exact), "dgim": (dgim_sketch, dgim_exact)}
    report = {}
    for name, (sketch, exact) in methods.items():
        row = {}
        for side, fn in (("sketch", sketch), ("exact", exact)):
            runs = [timed(fn, trace_memory=False) for _ in range(args.repeats)]
            answer, _, peak = timed(fn, trace_memory=True)
            row[side] = {"answer": answer,
                         "seconds": round(min(seconds for _, seconds, _ in runs), 3),
                         "all_seconds": [round(seconds, 3) for _, seconds, _ in runs],
                         "peak_traced_mb": round(peak, 1)}
        row["error_pct"] = percent_error(row["sketch"]["answer"], row["exact"]["answer"])
        row["sketch_vs_exact_time"] = round(row["sketch"]["seconds"] / row["exact"]["seconds"], 1)
        report[name] = row
        print(f"{name:5s} sketch {row['sketch']['seconds']:7.2f} s  exact {row['exact']['seconds']:7.2f} s"
              f"  sketch mem {row['sketch']['peak_traced_mb']:7.1f} MB"
              f"  exact mem {row['exact']['peak_traced_mb']:7.1f} MB", file=sys.stderr)

    result = {
        "hours": [hour for hour, *_ in hours],
        "lines": len(all_views),
        "bloom_build_lines": len(build_hashes),
        "bloom_probe_lines": len(probe_hashes),
        "load_parse_hash_seconds": round(load_seconds, 2),
        "repeats": args.repeats,
        "algorithms": report,
        "machine": f"{platform.system()} {platform.release()} {platform.machine()}",
        "python": platform.python_version(),
        "note": ("Times exclude reading, parsing and hashing (load_parse_hash_seconds, shared by "
                 "every method). Exact methods use Python set/dict, which run in C; the sketches "
                 "are pure Python. Peak memory is traced on a separate run."),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
