#!/usr/bin/env python3
"""Find near-duplicate passages across the Apollo 11 transcripts.

Pipeline: split each transcript into fixed word windows, shingle and hash each
window, compute minhash signatures, band them with LSH, then check everything
against exact Jaccard similarity computed with an inverted index.

Pairs of overlapping windows from the same file are excluded everywhere: they
share words by construction and are not interesting duplicates.
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time

import lsh
import minhash
import shingle


FILES = ("air-to-ground", "onboard-voice", "public-commentary")
SETTINGS = ((20, 5), (25, 4), (10, 10))  # (bands, rows); each uses n = 100 rows


class Timer:
    """Record wall-clock seconds for each named step with a monotonic clock."""

    def __init__(self):
        self.steps = []

    def run(self, label, func, *args):
        started = time.perf_counter()
        result = func(*args)
        self.steps.append({"step": label, "seconds": round(time.perf_counter() - started, 3)})
        print(f"[{self.steps[-1]['seconds']:8.3f} s] {label}", flush=True)
        return result


def load_windows(text_dir, size, stride):
    """Return {window_id: (file, start, words)} for every transcript window."""
    windows = {}
    for name in FILES:
        tokens = shingle.words((text_dir / f"{name}.txt").read_text(encoding="utf-8"))
        for start in shingle.window_starts(len(tokens), size, stride):
            windows[f"{name}:{start:06d}"] = (name, start, tokens[start:start + size])
    return windows


def shingle_windows(windows, kind, k):
    sets = {}
    for wid, (_, _, tokens) in windows.items():
        raw = (shingle.word_shingles(tokens, k) if kind == "word"
               else shingle.char_shingles(" ".join(tokens), k))
        if raw:  # a window shorter than k has no shingles and cannot be compared
            sets[wid] = shingle.hashed(raw)
    return sets


def signatures(sets, params):
    return {wid: minhash.signature(s, params) for wid, s in sets.items()}


def trivial(windows, a, b, size):
    """True when two windows come from the same file and overlap."""
    fa, sa, _ = windows[a]
    fb, sb, _ = windows[b]
    return fa == fb and abs(sa - sb) < size


def exact_pairs(sets, windows, size, keep_from):
    """Exact Jaccard for every non-trivial pair sharing at least one shingle.

    An inverted index lists the windows containing each shingle, so only pairs
    with a shared shingle are ever touched. Every other pair has Jaccard 0.
    Returns (histogram of all pairs by 0.05 bin, {pair: J} for J >= keep_from).
    """
    index = defaultdict(list)
    for wid in sorted(sets):
        for x in sets[wid]:
            index[x].append(wid)
    histogram = Counter()
    kept = {}
    for a in sorted(sets):
        shared = Counter()
        for x in sets[a]:
            for b in index[x]:
                if b > a:
                    shared[b] += 1
        for b, inter in shared.items():
            if trivial(windows, a, b, size):
                continue
            j = inter / (len(sets[a]) + len(sets[b]) - inter)
            histogram[min(int(j * 20), 19)] += 1
            if j >= keep_from:
                kept[(a, b)] = j
    return histogram, kept


def cross(pair):
    return pair[0].split(":")[0] != pair[1].split(":")[0]


def estimate_errors(truth, sigs, n):
    """Minhash estimate minus exact Jaccard, grouped into 0.1 bins."""
    bins = defaultdict(list)
    for (a, b), j in truth.items():
        bins[min(int(j * 10), 9)].append(minhash.estimate(sigs[a], sigs[b]) - j)
    rows = []
    for k in sorted(bins):
        errs = bins[k]
        mid = (k + 0.5) / 10
        rows.append({
            "bin": f"{k / 10:.1f}-{(k + 1) / 10:.1f}",
            "pairs": len(errs),
            "mean_error": round(sum(errs) / len(errs), 4),
            "mean_abs_error": round(sum(abs(e) for e in errs) / len(errs), 4),
            "rmse": round(math.sqrt(sum(e * e for e in errs) / len(errs)), 4),
            "theory_sd_at_mid": round(math.sqrt(mid * (1 - mid) / n), 4),
        })
    every = [e for errs in bins.values() for e in errs]
    summary = {
        "pairs": len(every),
        "mean_abs_error": round(sum(abs(e) for e in every) / len(every), 4),
        "rmse": round(math.sqrt(sum(e * e for e in every) / len(every)), 4),
        "one_over_sqrt_n": round(1 / math.sqrt(n), 4),
        "within_one_over_sqrt_n": round(sum(abs(e) <= 1 / math.sqrt(n) for e in every) / len(every), 4),
    }
    return rows, summary


def evaluate(cands, truth, sets, sigs, threshold_j, only_cross):
    """Recall and precision of a candidate set against exact Jaccard."""
    pick = (lambda p: cross(p)) if only_cross else (lambda p: True)
    cands = {p for p in cands if pick(p)}
    true_pairs = {p for p, j in truth.items() if j >= threshold_j and pick(p)}

    def exact(p):
        return truth.get(p) if p in truth else minhash.jaccard(sets[p[0]], sets[p[1]])

    hits = sum(1 for p in cands if exact(p) >= threshold_j)
    verified = {p for p in cands if minhash.estimate(sigs[p[0]], sigs[p[1]]) >= threshold_j}
    verified_hits = sum(1 for p in verified if exact(p) >= threshold_j)
    return {
        "true_pairs": len(true_pairs),
        "candidates": len(cands),
        "recall": round(len(cands & true_pairs) / len(true_pairs), 4) if true_pairs else None,
        "precision": round(hits / len(cands), 4) if cands else None,
        "verified_candidates": len(verified),
        "verified_recall": round(len(verified & true_pairs) / len(true_pairs), 4) if true_pairs else None,
        "verified_precision": round(verified_hits / len(verified), 4) if verified else None,
    }


def s_curve(histogram, truth, cands, b, r):
    """Measured candidate rate per 0.05 Jaccard bin next to 1-(1-s^r)^b.

    Bins below the kept-pairs floor count all pairs from the histogram, but
    candidates there are counted only if they appear among kept pairs, so
    measured rates are reported only for bins fully covered by `truth`.
    """
    in_bin = defaultdict(list)
    for p, j in truth.items():
        in_bin[min(int(j * 20), 19)].append((p, j))
    rows = []
    for k in sorted(in_bin):
        members = in_bin[k]
        if len(members) != histogram[k]:
            continue
        mean_theory = sum(lsh.probability(j, b, r) for _, j in members) / len(members)
        measured = sum(p in cands for p, _ in members) / len(members)
        rows.append({"bin": f"{k / 20:.2f}-{(k + 1) / 20:.2f}", "pairs": len(members),
                     "measured": round(measured, 4), "theory": round(mean_theory, 4)})
    return rows


def excerpt(tokens, n=14):
    return " ".join(tokens[:n]) + (" ..." if len(tokens) > n else "")


def top_pairs(truth, windows, size, limit):
    """Highest-Jaccard cross-file pairs, skipping overlaps of pairs already shown."""
    shown = []
    for (a, b), j in sorted(truth.items(), key=lambda kv: (-kv[1], kv[0])):
        if not cross((a, b)):
            continue
        if any(trivial(windows, a, x, size) and trivial(windows, b, y, size) for x, y, _ in shown):
            continue
        shown.append((a, b, j))
        if len(shown) == limit:
            break
    return [{"a": a, "b": b, "jaccard": round(j, 4),
             "a_text": excerpt(windows[a][2]), "b_text": excerpt(windows[b][2])}
            for a, b, j in shown]


def coverage(truth, windows, size, threshold_j):
    """Words in each file covered by a window with a cross-file match >= threshold."""
    covered = defaultdict(set)
    for (a, b), j in truth.items():
        if j >= threshold_j and cross((a, b)):
            for wid in (a, b):
                name, start, _ = windows[wid]
                covered[name].update(range(start, start + size))
    return {name: len(covered[name]) for name in FILES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-dir", type=Path, default=Path("data/apollo11/text"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--window", type=int, default=50)
    parser.add_argument("--stride", type=int, default=25)
    parser.add_argument("--shingle", choices=("word", "char"), default="word")
    parser.add_argument("-k", type=int, nargs="+", default=[3, 5])
    parser.add_argument("--threshold", type=float, default=0.5, help="near-duplicate Jaccard")
    parser.add_argument("--final", default="3,25,4", help="k,b,r used for Hadoop and top pairs")
    parser.add_argument("--seed", type=int, default=4099)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error(f"output already exists: {args.output_dir}")
    args.output_dir.mkdir(parents=True)
    final_k, final_b, final_r = (int(x) for x in args.final.split(","))

    timer = Timer()
    started_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = SETTINGS[0][0] * SETTINGS[0][1]
    params = minhash.hash_params(n, args.seed)
    windows = timer.run("split transcripts into windows", load_windows,
                        args.text_dir, args.window, args.stride)
    report = {"started_utc": started_utc, "window": args.window, "stride": args.stride,
              "shingle": args.shingle, "signature_rows": n, "seed": args.seed,
              "threshold": args.threshold, "windows": len(windows),
              "windows_per_file": dict(Counter(w[0] for w in windows.values())),
              "words_per_file": {name: max(start + len(tokens) for f, start, tokens
                                           in windows.values() if f == name) for name in FILES},
              "by_k": {}}

    for k in args.k:
        sets = timer.run(f"k={k}: shingle and hash windows", shingle_windows,
                         windows, args.shingle, k)
        sigs = timer.run(f"k={k}: minhash signatures (n={n})", signatures, sets, params)
        histogram, truth = timer.run(f"k={k}: exact Jaccard via inverted index",
                                     exact_pairs, sets, windows, args.window, 0.1)
        errors, error_summary = timer.run(f"k={k}: minhash estimate error",
                                          estimate_errors, truth, sigs, n)
        entry = {"windows_with_shingles": len(sets),
                 "pairs_sharing_a_shingle": sum(histogram.values()),
                 "jaccard_histogram": {f"{b / 20:.2f}": histogram[b] for b in sorted(histogram)},
                 "cross_file_words_covered": coverage(truth, windows, args.window, args.threshold),
                 "estimate_error": error_summary, "estimate_error_bins": errors, "settings": {}}
        for b, r in SETTINGS:
            raw = timer.run(f"k={k} b={b} r={r}: LSH banding", lsh.candidates, sigs, b, r)
            cands = {p for p in raw if not trivial(windows, p[0], p[1], args.window)}
            entry["settings"][f"b={b},r={r}"] = {
                "threshold": round(lsh.threshold(b, r), 4),
                "raw_candidates": len(raw),
                "all_pairs": evaluate(cands, truth, sets, sigs, args.threshold, False),
                "cross_file": evaluate(cands, truth, sets, sigs, args.threshold, True),
                "s_curve": s_curve(histogram, truth, cands, b, r),
            }
            if (k, b, r) == (final_k, final_b, final_r):
                with open(args.output_dir / "signatures.tsv", "w", encoding="utf-8") as out:
                    for wid in sorted(sigs):
                        out.write(wid + "\t" + " ".join(map(str, sigs[wid])) + "\n")
                with open(args.output_dir / "candidates-local.tsv", "w", encoding="utf-8") as out:
                    for a, c in sorted(raw):
                        out.write(f"{a}\t{c}\n")
                report["final"] = {"k": k, "b": b, "r": r,
                                   "threshold": round(lsh.threshold(b, r), 4),
                                   "top_pairs": top_pairs(truth, windows, args.window, 10)}
        report["by_k"][str(k)] = entry

    report["timings"] = timer.steps
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n",
                                                encoding="utf-8")
    print(f"Wrote {args.output_dir}/report.json")


if __name__ == "__main__":
    main()
