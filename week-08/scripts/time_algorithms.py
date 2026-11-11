#!/usr/bin/env python3
"""Time each sketch and each exact method on its own, over the whole day.

    nice python3 week-08/scripts/time_algorithms.py --input-dir data/week-08/pageviews \\
        --work-dir data/week-08/tmp --output week-08/results/full-day-per-algorithm.json

Every measurement is one streaming pass over the gzip files, run alone in a
fresh child process, one after another.  Nothing holds the day in memory.
For each pass we record the wall-clock seconds and the peak resident memory
the operating system reports for that process.

- Baseline: read, parse and hash every line, and do nothing else.  Every
  other pass pays this cost too.  It runs first and again last, so the gap
  between the two shows how much the timings wobble.
- Sketch passes: feed the hashes to one sketch class (Bloom, FM, AMS, DGIM).
- Exact passes: the method the full run uses.  Bloom, FM and AMS write the
  hashes to 64 partition files on disk, then total one partition at a time.
  DGIM keeps the positions of the hot lines inside the window.

The exact totals use Python's ``set`` and ``dict``, which run in C, while the
sketches are pure Python.  Read the result for memory, not speed.
"""

from __future__ import annotations

import argparse
from collections import deque
import gzip
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import platform
import resource
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dgim_reduced_error import DGIMReduced  # noqa: E402
from download_pageviews import parse_hours  # noqa: E402
from pageviews import (HashedBloom, HashedFM, WeightedAMS, _exact_recent,  # noqa: E402
                       _Partitions, find_files, percent_error)


def hashed_lines(path):
    """Yield (64-bit key hash, views) for every valid line of one gzip file."""
    blake, from_bytes = hashlib.blake2b, int.from_bytes
    with gzip.open(path, "rb") as handle:
        for line in handle:
            pieces = line.rsplit(b" ", 2)
            if len(pieces) != 3 or not pieces[1].isdigit() or b" " not in pieces[0]:
                continue
            yield from_bytes(blake(pieces[0], digest_size=8).digest(), "little"), int(pieces[1])


def baseline(files):
    """Read, parse and hash only.  Returns [lines, views]."""
    lines = views = 0
    for _, path in files:
        for _, c in hashed_lines(path):
            lines += 1
            views += c
    return [lines, views]


def bloom_sketch(files, capacity=60_000_000):
    bloom = HashedBloom.for_capacity(capacity, 0.01)
    for _, path in files[:-1]:
        for h, _ in hashed_lines(path):
            bloom.add_hash(h)
    return sum(1 for h, _ in hashed_lines(files[-1][1]) if bloom.contains_hash(h))


def fm_sketch(files):
    fm = HashedFM(12)
    for _, path in files:
        for h, _ in hashed_lines(path):
            fm.add_hash(h)
    return round(fm.estimate(), 1)


def ams_sketch(files):
    ams = WeightedAMS(4096, 4099, 8)
    for _, path in files:
        for h, c in hashed_lines(path):
            ams.add(h, c)
    return ams.estimate()


def dgim_sketch(files, threshold=100, window=1_000_000):
    dgim = DGIMReduced(window, r=2)
    t = 0
    for _, path in files:
        for _, c in hashed_lines(path):
            t += 1
            if c >= threshold:
                dgim.add_zeros(t - 1 - dgim.time)
                dgim.add(1)
    dgim.add_zeros(t - dgim.time)
    return dgim.estimate(max(1, min(window, t)))


def _spill(files, parts, with_views=False):
    """Write every line's hash (and views) to the partition files, one hour at a time."""
    hashes, values = parts.hashes, parts.values
    for _, path in files:
        for h, c in hashed_lines(path):
            hashes[h >> 58].append(h)
            if with_views:
                values[h >> 58].append(c)
        parts.flush()


def bloom_exact(files, work_dir=None):
    """Probe-hour pages that were truly seen in an earlier hour."""
    with tempfile.TemporaryDirectory(prefix="time-exact-", dir=work_dir) as work:
        built, probed = _Partitions(Path(work), "build"), _Partitions(Path(work), "probe")
        _spill(files[:-1], built)
        _spill(files[-1:], probed)
        return sum(len(set(built.load(part)[0]).intersection(probed.load(part)[0]))
                   for part in range(_Partitions.PARTS))


def fm_exact(files, work_dir=None):
    """Distinct pages in the day."""
    with tempfile.TemporaryDirectory(prefix="time-exact-", dir=work_dir) as work:
        parts = _Partitions(Path(work), "all")
        _spill(files, parts)
        return sum(len(set(parts.load(part)[0])) for part in range(_Partitions.PARTS))


def ams_exact(files, work_dir=None):
    """Second moment: the sum of (views per page) squared."""
    with tempfile.TemporaryDirectory(prefix="time-exact-", dir=work_dir) as work:
        parts = _Partitions(Path(work), "all")
        _spill(files, parts, with_views=True)
        f2 = 0
        for part in range(_Partitions.PARTS):
            totals = {}
            get = totals.get
            for h, c in zip(*parts.load(part)):
                totals[h] = get(h, 0) + c
            f2 += sum(v * v for v in totals.values())
        return f2


def dgim_exact(files, threshold=100, window=1_000_000):
    hot = deque()
    t = 0
    for _, path in files:
        for _, c in hashed_lines(path):
            t += 1
            if c >= threshold:
                hot.append(t)
                while hot[0] <= t - window:
                    hot.popleft()
    return _exact_recent(hot, t, max(1, min(window, t)))


def _timed(fn, args, kwargs):
    started = time.perf_counter()
    answer = fn(*args, **kwargs)
    return {"answer": answer, "pass_seconds": round(time.perf_counter() - started, 1),
            "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)}


def alone(fn, *args, **kwargs):
    """Run ``fn`` in a fresh child process so its time and peak memory are its own."""
    with multiprocessing.get_context("fork").Pool(1) as pool:
        return pool.apply(_timed, (fn, args, kwargs))


def measure(files, work_dir=None, threshold=100, window=1_000_000, say=lambda message: None):
    """Run every pass, one at a time, and return the report."""
    files = sorted(files)
    stream = dict(threshold=threshold, window=window)
    passes = [("bloom", bloom_sketch, {}, bloom_exact, dict(work_dir=work_dir)),
              ("fm", fm_sketch, {}, fm_exact, dict(work_dir=work_dir)),
              ("ams", ams_sketch, {}, ams_exact, dict(work_dir=work_dir)),
              ("dgim", dgim_sketch, stream, dgim_exact, stream)]
    started = time.perf_counter()
    first = alone(baseline, files)
    say(f"baseline {first['pass_seconds']} s")
    algorithms = {}
    for name, sketch, sketch_args, exact, exact_args in passes:
        row = {"sketch": alone(sketch, files, **sketch_args),
               "exact": alone(exact, files, **exact_args)}
        row["estimate"] = row["sketch"].pop("answer")
        row["exact_answer"] = row["exact"].pop("answer")
        row["error_pct"] = percent_error(row["estimate"], row["exact_answer"])
        algorithms[name] = row
        say(f"{name}: sketch {row['sketch']} exact {row['exact']}")
    last = alone(baseline, files)
    lines, views = first.pop("answer")
    return {
        "dataset": {"hours": [hour for hour, _ in files], "lines": lines, "views": views,
                    "bytes_gz": sum(path.stat().st_size for _, path in files)},
        "baseline_read_parse_hash": {"first": first, "last": {k: last[k] for k in first}},
        "algorithms": algorithms,
        "total_wall_seconds": round(time.perf_counter() - started, 1),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--hours", default="00-23")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=None,
                        help="folder for the temporary exact-answer partitions (default: system temp)")
    args = parser.parse_args(argv)

    files = find_files(args.input_dir, set(parse_hours(args.hours)))
    if len(files) < 2:
        parser.error("need at least 2 hours: earlier hours build the Bloom filter, the last probes it")
    if args.work_dir is not None:
        args.work_dir.mkdir(parents=True, exist_ok=True)
    result = measure(files, args.work_dir,
                     say=lambda message: print(message, file=sys.stderr, flush=True))
    result.update({
        "machine": f"{platform.system()} {platform.release()} {platform.machine()}, "
                   f"{os.cpu_count()} cores",
        "python": platform.python_version(),
        "note": ("Each pass ran once, alone, in its own process. pass_seconds includes reading, "
                 "parsing and hashing (see baseline_read_parse_hash). peak_rss_mb is that "
                 "process's peak resident memory. Exact methods for Bloom, FM and AMS write "
                 "hashes to 64 partition files and total one partition at a time with Python "
                 "set/dict, which run in C; the sketches are pure Python."),
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
