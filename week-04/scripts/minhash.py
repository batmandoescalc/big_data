#!/usr/bin/env python3
"""MinHash signatures (MMDS Section 3.3) and Jaccard similarity (Section 3.1).

Each of the n rows uses a random hash h(x) = (a*x + b) mod p with the prime
p = 2^61 - 1. Because p is far larger than any 32-bit shingle hash, h acts as
a random reordering of the shingles, standing in for a random permutation of
the characteristic matrix's rows.
"""

import random


PRIME = (1 << 61) - 1


def hash_params(n, seed):
    """Return n (a, b) pairs from a seeded generator, so runs are repeatable."""
    rng = random.Random(seed)
    return [(rng.randrange(1, PRIME), rng.randrange(0, PRIME)) for _ in range(n)]


def signature(shingle_hashes, params):
    """Return the minhash signature of a non-empty set of integer shingles."""
    if not shingle_hashes:
        raise ValueError("an empty set has no minhash signature")
    values = list(shingle_hashes)
    return [min((a * x + b) % PRIME for x in values) for a, b in params]


def jaccard(a, b):
    """Exact Jaccard similarity |A n B| / |A u B| of two sets."""
    if not a and not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def estimate(sig_a, sig_b):
    """Estimated Jaccard: the fraction of signature rows that agree."""
    if len(sig_a) != len(sig_b):
        raise ValueError("signatures must have the same length")
    return sum(x == y for x, y in zip(sig_a, sig_b)) / len(sig_a)
