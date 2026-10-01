#!/usr/bin/env python3
"""Locality-sensitive hashing by banding (MMDS Section 3.4).

A signature of b*r rows is cut into b bands of r rows. Two items become a
candidate pair if they agree on every row of at least one band. Band keys are
a stable SHA-1 digest, so this module and the Hadoop mapper bucket identically.
"""

from collections import defaultdict
import hashlib
from itertools import combinations


def threshold(b, r):
    """Similarity where the S-curve is steepest, about (1/b)^(1/r)."""
    return (1 / b) ** (1 / r)


def probability(s, b, r):
    """Chance that a pair with Jaccard similarity s becomes a candidate."""
    return 1 - (1 - s ** r) ** b


def band_keys(sig, b, r):
    """Yield one 'band:digest' bucket key per band of a signature."""
    if len(sig) != b * r:
        raise ValueError(f"signature has {len(sig)} rows, expected b*r = {b * r}")
    for band in range(b):
        rows = ",".join(str(v) for v in sig[band * r:(band + 1) * r])
        digest = hashlib.sha1(rows.encode("ascii")).hexdigest()[:16]
        yield f"{band}:{digest}"


def pairs_in_bucket(members):
    """All unordered pairs in one bucket, smaller ID first, in a fixed order."""
    return combinations(sorted(set(members)), 2)


def candidates(signatures, b, r):
    """Return the set of candidate pairs (id1, id2) with id1 < id2.

    `signatures` maps an item ID to its signature list.
    """
    buckets = defaultdict(list)
    for item, sig in signatures.items():
        for key in band_keys(sig, b, r):
            buckets[key].append(item)
    found = set()
    for members in buckets.values():
        if len(members) > 1:
            found.update(pairs_in_bucket(members))
    return found


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Print the LSH threshold and S-curve.")
    parser.add_argument("-b", type=int, required=True, help="number of bands")
    parser.add_argument("-r", type=int, required=True, help="rows per band")
    args = parser.parse_args()
    print(f"b={args.b} r={args.r} n={args.b * args.r} "
          f"threshold (1/b)^(1/r) = {threshold(args.b, args.r):.3f}")
    for tenth in range(11):
        s = tenth / 10
        print(f"s={s:.1f}  P(candidate)={probability(s, args.b, args.r):.4f}")


if __name__ == "__main__":
    main()
