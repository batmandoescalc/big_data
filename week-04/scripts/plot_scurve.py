#!/usr/bin/env python3
"""Plot measured vs theoretical LSH S-curves from a find_similar.py report.

Uses matplotlib when it is installed; otherwise prints the same data as a
Markdown table. The pipeline itself needs only the standard library.
"""

import argparse
import json
from pathlib import Path

import lsh


def table(report, k):
    lines = []
    for setting, data in report["by_k"][k]["settings"].items():
        lines += [f"\n{setting} (threshold {data['threshold']:.3f})\n",
                  "| Jaccard bin | Pairs | Measured | Theory |", "| --- | ---: | ---: | ---: |"]
        lines += [f"| {row['bin']} | {row['pairs']:,} | {row['measured']:.3f} | {row['theory']:.3f} |"
                  for row in data["s_curve"]]
    return "\n".join(lines)


def plot(report, k, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ink, muted, accent, surface = "#0b0b0b", "#52514e", "#2a78d6", "#fcfcfb"
    settings = report["by_k"][k]["settings"]
    fig, axes = plt.subplots(1, len(settings), figsize=(12, 4), sharey=True, facecolor=surface)
    for ax, (setting, data) in zip(axes, settings.items()):
        b, r = (int(part.split("=")[1]) for part in setting.split(","))
        xs = [i / 200 for i in range(201)]
        ax.plot(xs, [lsh.probability(s, b, r) for s in xs], color=muted, linewidth=2,
                label="theory: 1-(1-s^r)^b")
        mids = [sum(float(v) for v in row["bin"].split("-")) / 2 for row in data["s_curve"]]
        ax.plot(mids, [row["measured"] for row in data["s_curve"]], "o", color=accent,
                markersize=8, markeredgecolor=surface, markeredgewidth=2, label="measured")
        ax.axvline(data["threshold"], color=muted, linewidth=1, linestyle=":")
        ax.text(data["threshold"] + 0.02, 0.05, f"t = {data['threshold']:.2f}", color=muted)
        ax.set_title(f"b = {b}, r = {r}", color=ink)
        ax.set_xlabel("exact Jaccard similarity", color=muted)
        ax.set_xlim(0, 1)
        ax.set_facecolor(surface)
        ax.grid(color="#e4e3df", linewidth=0.8)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#c9c8c2")
        ax.tick_params(colors=muted)
    axes[0].set_ylabel("share of pairs that became candidates", color=muted)
    axes[-1].legend(frameon=False, loc="upper left")  # empty region left of the steep r=10 curve
    fig.suptitle(f"LSH S-curves, word {k}-shingles, n = {report['signature_rows']} "
                 f"(pairs with exact Jaccard >= 0.10)", color=ink)
    fig.tight_layout()
    fig.savefig(output, dpi=150, facecolor=surface)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--k", default="3")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    try:
        plot(report, args.k, args.output)
        print(f"Wrote {args.output}")
    except ImportError:
        print("matplotlib is not installed; printing the S-curve table instead.")
        print(table(report, args.k))


if __name__ == "__main__":
    main()
