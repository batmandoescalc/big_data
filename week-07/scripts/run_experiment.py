#!/usr/bin/env python3
"""Compare exact stream answers with four bounded-memory Chapter 4 sketches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
import tracemalloc

from event_generator import generate_events
from streaming import (AMSSecondMoment, BloomFilter, DGIM, FlajoletMartin,
                       exact_recent_ones, exact_second_moment)


def percent_error(estimate, exact):
    """Return percentage error, treating two zero values as an exact match."""
    return 0.0 if exact == 0 else abs(estimate - exact) / exact * 100


def run(events, window, registers, estimators, bloom_bits, bloom_hashes):
    """Process an iterable once, preserving exact values only for the comparison."""
    bloom = BloomFilter(bloom_bits, bloom_hashes)
    fm = FlajoletMartin(registers)
    ams = AMSSecondMoment(estimators)
    dgim = DGIM(window)
    users, statuses = [], []

    started = time.perf_counter()
    tracemalloc.start()
    for event in events:
        user = event["user_id"]
        error = event["status"] >= 500
        bloom.add(user)
        fm.add(user)
        ams.add(user)
        dgim.add(error)
        # These reference lists deliberately make the exact baseline grow with
        # the stream.  The sketches above do not retain the event stream.
        users.append(user)
        statuses.append(error)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    elapsed = time.perf_counter() - started

    exact_distinct = len(set(users))
    exact_f2 = exact_second_moment(users)
    recent = min(window, len(statuses))
    exact_ones = exact_recent_ones(statuses, recent) if recent else 0
    false_positive_probes = [f"never-seen-{index}" for index in range(1_000)]
    false_positive_rate = sum(probe in bloom for probe in false_positive_probes) / len(false_positive_probes)

    return {
        "schema_version": 1,
        "engine": "local-python",
        "elapsed_seconds": round(elapsed, 6),
        "python_peak_bytes_including_exact_baseline": peak,
        "events": len(users),
        "window": window,
        "results": {
            "bloom_filter": {
                "logical_memory_bytes": bloom.memory_bytes,
                "false_positive_rate_on_1000_absent_probes": false_positive_rate,
            },
            "flajolet_martin": {
                "exact_distinct_users": exact_distinct,
                "estimate": fm.estimate(),
                "percent_error": percent_error(fm.estimate(), exact_distinct),
                "logical_memory_bytes": fm.memory_bytes,
            },
            "ams_second_moment": {
                "exact_f2": exact_f2,
                "estimate": ams.estimate(),
                "percent_error": percent_error(ams.estimate(), exact_f2),
                "logical_memory_bytes": ams.memory_bytes,
            },
            "dgim_recent_errors": {
                "exact_ones": exact_ones,
                "estimate": dgim.estimate(recent) if recent else 0,
                "percent_error": percent_error(dgim.estimate(recent) if recent else 0, exact_ones),
                "logical_memory_bytes": dgim.memory_bytes,
            },
        },
    }


def main():
    """Parse a reproducible experiment configuration and write a JSON report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=100_000)
    parser.add_argument("--users", type=int, default=10_000)
    parser.add_argument("--pages", type=int, default=5_000)
    parser.add_argument("--error-rate", type=float, default=0.03)
    parser.add_argument("--seed", type=int, default=4099)
    parser.add_argument("--skewed", action="store_true")
    parser.add_argument("--window", type=int, default=1_024)
    parser.add_argument("--registers", type=int, default=128)
    parser.add_argument("--estimators", type=int, default=512)
    parser.add_argument("--bloom-bits", type=int, default=131_072)
    parser.add_argument("--bloom-hashes", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    event_args = {key: getattr(args, key) for key in
                  ("count", "users", "pages", "error_rate", "seed", "skewed")
                  if hasattr(args, key)}
    event_args["count"] = args.events
    result = run(generate_events(**event_args), args.window, args.registers,
                 args.estimators, args.bloom_bits, args.bloom_hashes)
    result["generator"] = event_args
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
