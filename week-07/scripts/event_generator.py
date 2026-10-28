#!/usr/bin/env python3
"""Generate deterministic JSON-line click events without retaining the stream."""

from __future__ import annotations

import argparse
import json
import random
import sys


def generate_events(count, users, pages, error_rate, seed, skewed=False):
    """Yield reproducible event records one at a time."""
    if count < 0 or users < 1 or pages < 1 or not 0 <= error_rate <= 1:
        raise ValueError("invalid generator parameters")
    rng = random.Random(seed)
    for sequence in range(1, count + 1):
        # The skewed mode creates a few genuinely popular values without
        # duplicating the stream merely to inflate its size.
        user_limit = max(1, users // 10) if skewed and rng.random() < 0.8 else users
        page_limit = max(1, pages // 10) if skewed and rng.random() < 0.8 else pages
        yield {
            "sequence": sequence,
            "user_id": f"user-{rng.randrange(user_limit):05d}",
            "page_id": f"page-{rng.randrange(page_limit):05d}",
            "status": 500 if rng.random() < error_rate else 200,
        }


def main():
    """Write the requested event stream as newline-delimited JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=100_000)
    parser.add_argument("--users", type=int, default=10_000)
    parser.add_argument("--pages", type=int, default=5_000)
    parser.add_argument("--error-rate", type=float, default=0.03)
    parser.add_argument("--seed", type=int, default=4099)
    parser.add_argument("--skewed", action="store_true")
    args = parser.parse_args()
    for event in generate_events(**vars(args)):
        print(json.dumps(event, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
