#!/usr/bin/env python3
"""Measure how section 4.6.6 (r buckets per size) shrinks DGIM's error.

For each r, one DGIMReduced sketch reads the same bit stream.  At many query
times, for many window lengths k, the sketch's estimate is compared with the
exact count of ones in the last k bits.  Two streams are used:

* wikipedia: one hour of Wikimedia pageviews, one line per bit, in file order;
  bit = 1 when the line's view count is at least --threshold (a "hot" page).
* synthetic: independent coin flips with probability --synthetic-p, seeded.

Writes a JSON report and a stdlib SVG chart.  Example:

    python3 week-08/scripts/dgim_study.py \\
      --pageviews data/week-08/dgim-sample/pageviews-20261027-120000.gz \\
      --output data/week-08/results/dgim-study.json \\
      --chart week-08/docs/dgim-4.6.6.svg
"""

from __future__ import annotations

import argparse
from array import array
import gzip
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import time

from dgim_reduced_error import DGIMReduced


def wikipedia_bits(path, threshold, max_lines=None):
    """Yield 1 for each pageviews line with views >= threshold, else 0."""
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle):
            if max_lines is not None and number >= max_lines:
                return
            parts = line.split(" ")
            try:
                views = int(parts[2])
            except (IndexError, ValueError):
                yield 0  # malformed line: keep stream positions, count as cold
                continue
            yield 1 if views >= threshold else 0


def synthetic_bits(length, probability, seed):
    """Yield ``length`` independent bits that are 1 with ``probability``."""
    rng = random.Random(seed)
    for _ in range(length):
        yield 1 if rng.random() < probability else 0


def query_lengths(window, count, seed):
    """Return sorted distinct k values: log-spaced plus seeded uniform ones."""
    ks = {window, 1}
    half = count // 2
    for index in range(half):
        ks.add(max(1, round(window ** (index / max(1, half - 1)))))
    rng = random.Random(seed)
    while len(ks) < count:
        ks.add(rng.randint(1, window))
    return sorted(ks)


def week07_estimate(buckets, now, last):
    """Week 7's DGIM.estimate rule, applied to a newest-first bucket list.

    It counts every bucket whose timestamp is inside the range in full, then
    adds half of the first bucket whose timestamp is outside the range.  That
    is not the textbook rule (section 4.6.4 halves the oldest bucket that is
    still inside), so it is reported separately as "week-07 as shipped".
    """
    cutoff = now - last
    total = 0.0
    for size, timestamp in buckets:
        if timestamp > cutoff:
            total += size
        else:
            total += size / 2
            break
    return total


def run_stream(name, bits, window, rs, query_times, ks, seed):
    """Feed one stream to every sketch; return per-r error and memory evidence."""
    sketches = {r: DGIMReduced(window, r) for r in rs}
    # Every r is scored on the same queries: those whose exact count exceeds
    # the largest r.  Then the half-counted bucket always has size >= 2, which
    # is what the book's error analysis assumes.  Ranges holding 1..max(r)
    # ones are reported separately ("small counts").
    min_count = max(rs) + 1
    prefix = array("q", [0])  # prefix[t] = ones among the first t bits
    errors = {r: [] for r in rs}
    small = {r: {"queries": 0, "max_error": 0.0, "max_error_size2_plus": 0.0} for r in rs}
    legacy = []
    bucket_counts = {r: [] for r in rs}
    started = time.perf_counter()
    ones = 0
    query_set = set(query_times)
    for t, bit in enumerate(bits, start=1):
        ones += bit
        prefix.append(ones)
        for sketch in sketches.values():
            sketch.add(bit)
        if t not in query_set:
            continue
        for r, sketch in sketches.items():
            bucket_counts[r].append(sketch.bucket_count)
            for k in ks:
                exact = ones - prefix[t - k]
                if exact == 0:
                    continue
                estimate, boundary = sketch.estimate_detail(k)
                error = abs(estimate - exact) / exact
                if exact >= min_count:
                    errors[r].append(error)
                    if r == 2:
                        old = week07_estimate(sketch.buckets, t, k)
                        legacy.append(abs(old - exact) / exact)
                else:
                    small[r]["queries"] += 1
                    small[r]["max_error"] = max(small[r]["max_error"], error)
                    if boundary >= 2:
                        small[r]["max_error_size2_plus"] = max(
                            small[r]["max_error_size2_plus"], error)
    length = len(prefix) - 1
    elapsed = time.perf_counter() - started
    asked = [q for q in query_times if q <= length]
    rows = []
    for r in rs:
        errs = sorted(errors[r])
        bound = 1.0 / (r - 1)
        rows.append({
            "r": r,
            "book_bound": bound,
            "queries_checked": len(errs),
            "mean_error": statistics.fmean(errs) if errs else None,
            "median_error": statistics.median(errs) if errs else None,
            "p99_error": errs[int(0.99 * (len(errs) - 1))] if errs else None,
            "max_error": errs[-1] if errs else None,
            "bound_held": (errs[-1] <= bound
                           and small[r]["max_error_size2_plus"] <= bound) if errs else None,
            "small_count_queries": small[r]["queries"],
            "small_count_max_error": small[r]["max_error"],
            "mean_buckets": statistics.fmean(bucket_counts[r]) if bucket_counts[r] else None,
            "max_buckets": max(bucket_counts[r]) if bucket_counts[r] else None,
            "max_memory_bytes": max(bucket_counts[r]) * DGIMReduced.BYTES_PER_BUCKET
            if bucket_counts[r] else None,
        })
    return {
        "stream": name,
        "bits": length,
        "ones": ones,
        "query_times": len(asked),
        "k_values": len(ks),
        "min_exact_count_scored": min_count,
        "elapsed_seconds": round(elapsed, 2),
        "week07_as_shipped_r2": {
            "mean_error": statistics.fmean(legacy) if legacy else None,
            "max_error": max(legacy) if legacy else None,
            "queries": len(legacy),
        },
        "by_r": rows,
    }


def spaced_times(window, length, count, seed):
    """Return ``count`` seeded query times after the first full window."""
    if length <= window:
        raise ValueError("stream must be longer than the window")
    rng = random.Random(seed)
    step = (length - window) / count
    return sorted({window + int(step * i + rng.random() * step) + 1 for i in range(count)})


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def count_lines(path, max_lines=None):
    with gzip.open(path, "rb") as handle:
        total = sum(1 for _ in handle)
    return total if max_lines is None else min(total, max_lines)


# --- chart -------------------------------------------------------------------

STYLE = """
  .surface { fill: #fcfcfb; }
  .ink { fill: #0b0b0b; }
  .ink2 { fill: #52514e; }
  .axis { stroke: #8a8984; }
  .grid { stroke: #e4e3df; }
  .s1 { fill: #2a78d6; }
  .s2 { fill: #eb6834; }
  .bound { stroke: #0b0b0b; }
  text { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
  @media (prefers-color-scheme: dark) {
    .surface { fill: #1a1a19; }
    .ink { fill: #f0efec; }
    .ink2 { fill: #c3c2b7; }
    .axis { stroke: #8f8e88; }
    .grid { stroke: #34332f; }
    .s1 { fill: #3987e5; }
    .s2 { fill: #d95926; }
    .bound { stroke: #f0efec; }
  }
"""


def _nice_max(value):
    """Return a round axis top whose quarter ticks are round numbers too."""
    if value <= 0:
        return 1.0
    quarter = value / 4
    power = 10 ** math.floor(math.log10(quarter))
    for step in (1, 2, 2.5, 3, 5, 10):
        if step * power >= quarter:
            return 4 * step * power
    return 40 * power


def _panel(parts, x0, y0, width, height, title, rs, series, fmt, bounds=None):
    """Draw one grouped-bar panel: one group per r, one bar per stream."""
    top = max([v for _, values in series for v in values] + (bounds or [0]))
    ymax = _nice_max(top * 1.05)
    left, bottom = 52, 34
    pw, ph = width - left - 8, height - bottom - 28
    px, py = x0 + left, y0 + 28
    parts.append(f'<text class="ink" x="{x0}" y="{y0 + 14}" font-size="14" font-weight="600">{title}</text>')
    for i in range(5):
        value = ymax * i / 4
        y = py + ph - ph * i / 4
        parts.append(f'<line class="grid" x1="{px}" y1="{y:.1f}" x2="{px + pw}" y2="{y:.1f}" stroke-width="1"/>')
        parts.append(f'<text class="ink2" x="{px - 6}" y="{y + 4:.1f}" font-size="11" text-anchor="end">{fmt(value)}</text>')
    parts.append(f'<line class="axis" x1="{px}" y1="{py + ph}" x2="{px + pw}" y2="{py + ph}" stroke-width="1"/>')
    group = pw / len(rs)
    bar = min(22, (group - 16) / len(series))
    for gi, r in enumerate(rs):
        gx = px + group * gi + (group - bar * len(series) - 2 * (len(series) - 1)) / 2
        for si, (css, values) in enumerate(series):
            value = values[gi]
            h = ph * value / ymax
            x = gx + si * (bar + 2)
            y = py + ph - h
            rad = min(4, h / 2, bar / 2)
            # Rounded data end at the top, square at the baseline.
            parts.append(
                f'<path class="{css}" d="M{x:.1f},{py + ph:.1f} V{y + rad:.1f} '
                f'Q{x:.1f},{y:.1f} {x + rad:.1f},{y:.1f} H{x + bar - rad:.1f} '
                f'Q{x + bar:.1f},{y:.1f} {x + bar:.1f},{y + rad:.1f} V{py + ph:.1f} Z">'
                f'<title>r={r}: {fmt(value)}</title></path>')
        if bounds:
            by = py + ph - ph * bounds[gi] / ymax
            parts.append(f'<line class="bound" x1="{gx - 5:.1f}" y1="{by:.1f}" '
                         f'x2="{gx + bar * len(series) + 7:.1f}" y2="{by:.1f}" '
                         f'stroke-width="2" stroke-dasharray="4 3"/>')
        label = f"r={r}" + (" (before)" if r == 2 else "")
        parts.append(f'<text class="ink2" x="{px + group * gi + group / 2:.1f}" y="{py + ph + 16}" '
                     f'font-size="11" text-anchor="middle">{label}</text>')
    parts.append(f'<text class="ink2" x="{px + pw / 2:.1f}" y="{py + ph + 31}" font-size="11" '
                 f'text-anchor="middle">r = buckets kept per size</text>')


def svg_chart(report):
    """Return an SVG with worst error, average error and memory, by r."""
    streams = report["streams"]
    rs = [row["r"] for row in streams[0]["by_r"]]
    names = {"wikipedia": "Wikipedia hot pages", "synthetic": "Synthetic coin flips"}
    css = ["s1", "s2"]

    def values(key, scale=1.0):
        return [(css[i], [row[key] * scale for row in stream["by_r"]])
                for i, stream in enumerate(streams)]

    width, height = 960, 396
    pct = lambda v: f"{v:.0f}%" if v >= 10 or v == int(v) else f"{v:.1f}%"
    kib = lambda v: f"{v / 1024:.1f} KiB" if v else "0"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="DGIM error and memory for r = {", ".join(map(str, rs))}">',
        f"<style>{STYLE}</style>",
        f'<rect class="surface" width="{width}" height="{height}" rx="8"/>',
        '<text class="ink" x="20" y="30" font-size="18" font-weight="600">'
        'Keeping more buckets per size shrinks DGIM\'s counting error</text>',
        '<text class="ink2" x="20" y="50" font-size="12">'
        f'Window N = {report["window"]:,} bits. Error = |estimate - exact| / exact, over '
        f'{streams[0]["query_times"]} query times x {streams[0]["k_values"]} range lengths</text>',
        '<text class="ink2" x="20" y="66" font-size="12">'
        f'(ranges holding at least {streams[0]["min_exact_count_scored"]} ones). '
        'Dashed line = the textbook worst case, 1/(r-1).</text>',
    ]
    panel_w = (width - 40) / 3
    _panel(parts, 20, 86, panel_w - 10, 260, "Worst error seen", rs,
           values("max_error", 100), pct, [100 / (r - 1) for r in rs])
    _panel(parts, 20 + panel_w, 86, panel_w - 10, 260, "Average error", rs,
           values("mean_error", 100), pct)
    _panel(parts, 20 + 2 * panel_w, 86, panel_w - 10, 260, "Memory (largest seen)", rs,
           values("max_memory_bytes"), kib)
    lx = 20
    for i, stream in enumerate(streams):
        parts.append(f'<rect class="{css[i]}" x="{lx}" y="{height - 24}" width="12" height="12" rx="2"/>')
        label = f'{names.get(stream["stream"], stream["stream"])} ({stream["ones"]:,} ones in {stream["bits"]:,} bits)'
        parts.append(f'<text class="ink" x="{lx + 18}" y="{height - 14}" font-size="12">{label}</text>')
        lx += 18 + 7.2 * len(label) + 24
    parts.append(f'<line class="bound" x1="{lx}" y1="{height - 18}" x2="{lx + 22}" y2="{height - 18}" '
                 'stroke-width="2" stroke-dasharray="4 3"/>')
    parts.append(f'<text class="ink" x="{lx + 28}" y="{height - 14}" font-size="12">bound 1/(r-1)</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pageviews", type=Path,
                        help="hourly pageviews .gz; omit to run the synthetic stream only")
    parser.add_argument("--threshold", type=int, default=100,
                        help="views at or above this make a line a 1 (default 100)")
    parser.add_argument("--max-lines", type=int, help="read only this many pageviews lines")
    parser.add_argument("--window", type=int, default=1_000_000)
    parser.add_argument("--rs", default="2,3,5,9")
    parser.add_argument("--query-times", type=int, default=200)
    parser.add_argument("--k-values", type=int, default=60)
    parser.add_argument("--synthetic-length", type=int, default=3_000_000)
    parser.add_argument("--synthetic-p", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=4099)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chart", type=Path, required=True)
    args = parser.parse_args()

    rs = sorted({int(value) for value in args.rs.split(",")})
    ks = query_lengths(args.window, args.k_values, args.seed)
    streams = []
    source = None
    if args.pageviews:
        length = count_lines(args.pageviews, args.max_lines)
        times = spaced_times(args.window, length, args.query_times, args.seed)
        streams.append(run_stream(
            "wikipedia", wikipedia_bits(args.pageviews, args.threshold, args.max_lines),
            args.window, rs, times, ks, args.seed))
        source = {"file": args.pageviews.name, "sha256": sha256(args.pageviews),
                  "threshold_views": args.threshold, "max_lines": args.max_lines}
    times = spaced_times(args.window, args.synthetic_length, args.query_times, args.seed)
    streams.append(run_stream(
        "synthetic", synthetic_bits(args.synthetic_length, args.synthetic_p, args.seed),
        args.window, rs, times, ks, args.seed))

    report = {
        "schema_version": 1,
        "window": args.window,
        "rs": rs,
        "seed": args.seed,
        "k_values": ks,
        "synthetic": {"length": args.synthetic_length, "p": args.synthetic_p},
        "wikipedia_source": source,
        "streams": streams,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.chart.parent.mkdir(parents=True, exist_ok=True)
    args.chart.write_text(svg_chart(report), encoding="utf-8")
    for stream in streams:
        print(stream["stream"], stream["bits"], "bits", stream["ones"], "ones",
              stream["elapsed_seconds"], "s")
        print("  week-07 as shipped (r=2):", stream["week07_as_shipped_r2"])
        for row in stream["by_r"]:
            print("  ", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()})


if __name__ == "__main__":
    main()
