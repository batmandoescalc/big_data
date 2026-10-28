#!/usr/bin/env python3
"""Repeat streaming-sketch runs at several sizes and write a JSON summary/SVG."""

from __future__ import annotations

import argparse
from collections import Counter, deque
import json
from pathlib import Path
import statistics
import sys
import time

from event_generator import generate_events
from streaming import AMSSecondMoment, BloomFilter, DGIM, FlajoletMartin


def percent_error(estimate, exact):
    """Return percentage error, with two zero values considered an exact match."""
    return 0.0 if exact == 0 else abs(estimate - exact) * 100 / exact


def exact_set_bytes(values):
    """Estimate retained set payload; Python's allocator overhead is excluded."""
    return sys.getsizeof(values) + sum(sys.getsizeof(value) for value in values)


def run_once(size, seed, *, users=None, registers=128, estimators=64):
    """Return exact and sketch evidence for one deterministic stream."""
    # Increase the possible distinct population with stream size.  A fixed
    # 1,000-user universe would make an exact set plateau immediately and
    # conceal the memory-growth contrast this benchmark is meant to show.
    users = users if users is not None else max(1_000, size // 10)
    bloom = BloomFilter(131_072, 5)
    fm = FlajoletMartin(registers)
    ams = AMSSecondMoment(estimators, seed)
    dgim = DGIM(1_024)
    exact_users, frequencies, recent = set(), Counter(), deque(maxlen=1_024)
    started = time.perf_counter()
    for event in generate_events(size, users, 100, 0.03, seed):
        user, error = event["user_id"], event["status"] >= 500
        bloom.add(user)
        fm.add(user)
        ams.add(user)
        dgim.add(error)
        exact_users.add(user)
        frequencies[user] += 1
        recent.append(error)
    elapsed = time.perf_counter() - started
    exact_f2 = sum(count * count for count in frequencies.values())
    exact_recent = sum(recent)
    return {
        "events": size,
        "seed": seed,
        "elapsed_seconds": elapsed,
        "exact": {
            "distinct": len(exact_users),
            "second_moment": exact_f2,
            "recent_errors": exact_recent,
            "logical_memory_bytes": exact_set_bytes(exact_users),
        },
        "sketches": {
            "bloom": {"logical_memory_bytes": bloom.memory_bytes},
            "fm": {
                "estimate": fm.estimate(),
                "percent_error": percent_error(fm.estimate(), len(exact_users)),
                "logical_memory_bytes": fm.memory_bytes,
            },
            "ams": {
                "estimate": ams.estimate(),
                "percent_error": percent_error(ams.estimate(), exact_f2),
                "logical_memory_bytes": ams.memory_bytes,
            },
            "dgim": {
                "estimate": dgim.estimate(),
                "percent_error": percent_error(dgim.estimate(), exact_recent),
                "logical_memory_bytes": dgim.memory_bytes,
            },
        },
    }


def summarize(runs):
    """Return median run-time/error and fixed-summary memory at each size."""
    summary = []
    for size in sorted({run["events"] for run in runs}):
        group = [run for run in runs if run["events"] == size]
        summary.append({
            "events": size,
            "runs": len(group),
            "median_elapsed_seconds": statistics.median(run["elapsed_seconds"] for run in group),
            "median_exact_set_bytes": statistics.median(
                run["exact"]["logical_memory_bytes"] for run in group),
            "bloom_bytes": group[0]["sketches"]["bloom"]["logical_memory_bytes"],
            "fm_bytes": group[0]["sketches"]["fm"]["logical_memory_bytes"],
            "ams_bytes": group[0]["sketches"]["ams"]["logical_memory_bytes"],
            "median_fm_error_percent": statistics.median(
                run["sketches"]["fm"]["percent_error"] for run in group),
            "median_ams_error_percent": statistics.median(
                run["sketches"]["ams"]["percent_error"] for run in group),
            "median_dgim_error_percent": statistics.median(
                run["sketches"]["dgim"]["percent_error"] for run in group),
        })
    return summary


def svg_chart(summary):
    """Draw a dependency-free memory chart suitable for repository documentation."""
    width, height, left, bottom = 700, 350, 80, 55
    plot_width, plot_height = width - left - 30, height - bottom - 35
    maximum = max(row["median_exact_set_bytes"] for row in summary) * 1.1
    colors = {"Exact set": "#d62728", "Bloom": "#1f77b4", "FM": "#2ca02c", "AMS": "#9467bd"}
    values = {
        "Exact set": [row["median_exact_set_bytes"] for row in summary],
        "Bloom": [row["bloom_bytes"] for row in summary],
        "FM": [row["fm_bytes"] for row in summary],
        "AMS": [row["ams_bytes"] for row in summary],
    }
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" role="img" aria-label="Memory versus stream size">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="{left}" y="24" font-family="sans-serif" font-size="17">Logical memory retained as stream size grows</text>',
             f'<line x1="{left}" y1="35" x2="{left}" y2="{height-bottom}" stroke="black"/>',
             f'<line x1="{left}" y1="{height-bottom}" x2="{width-20}" y2="{height-bottom}" stroke="black"/>']
    for fraction in (0, .25, .5, .75, 1):
        y = height - bottom - fraction * plot_height
        value = int(maximum * fraction / 1024)
        parts.extend([f'<line x1="{left-5}" y1="{y:.1f}" x2="{width-20}" y2="{y:.1f}" stroke="#ddd"/>',
                      f'<text x="5" y="{y+4:.1f}" font-family="sans-serif" font-size="11">{value} KiB</text>'])
    for index, row in enumerate(summary):
        x = left + (plot_width * index / max(1, len(summary)-1))
        parts.append(f'<text x="{x-14:.1f}" y="{height-28}" font-family="sans-serif" font-size="11">{row["events"]:,}</text>')
    for series, points in values.items():
        coordinates = []
        for index, value in enumerate(points):
            x = left + (plot_width * index / max(1, len(points)-1))
            y = height - bottom - value / maximum * plot_height
            coordinates.append(f"{x:.1f},{y:.1f}")
        parts.append(f'<polyline fill="none" stroke="{colors[series]}" stroke-width="3" points="{" ".join(coordinates)}"/>')
    for index, (series, color) in enumerate(colors.items()):
        x = left + index * 145
        parts.append(f'<rect x="{x}" y="{height-13}" width="10" height="10" fill="{color}"/><text x="{x+14}" y="{height-4}" font-family="sans-serif" font-size="11">{series}</text>')
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def main():
    """Repeat each requested size/seed pair and write reproducible evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", default="10000,25000,50000")
    parser.add_argument("--seeds", default="4099,4100,4101")
    # Smaller arrays keep the repeated comparison fast; the report records the
    # resulting logical memory rather than presenting it as the 128-register
    # demonstration configuration in README.md.
    parser.add_argument("--registers", type=int, default=32)
    parser.add_argument("--estimators", type=int, default=32)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chart", type=Path, required=True)
    args = parser.parse_args()
    sizes = [int(value) for value in args.sizes.split(",")]
    seeds = [int(value) for value in args.seeds.split(",")]
    runs = [run_once(size, seed, registers=args.registers, estimators=args.estimators)
            for size in sizes for seed in seeds]
    report = {"schema_version": 1, "sizes": sizes, "seeds": seeds,
              "runs": runs, "summary": summarize(runs)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.chart.parent.mkdir(parents=True, exist_ok=True)
    args.chart.write_text(svg_chart(report["summary"]), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
