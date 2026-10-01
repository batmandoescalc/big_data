#!/usr/bin/env python3
"""Read 'window_id<TAB>v1 v2 ... vn' signatures; emit one 'band:digest<TAB>window_id' per band.

Usage: python3 lsh_mapper.py BANDS ROWS. lsh.py ships alongside this file so
the cluster buckets exactly like the local pipeline.
"""

import sys

import lsh


def main():
    bands, rows = int(sys.argv[1]), int(sys.argv[2])
    for line in sys.stdin:
        window_id, values = line.rstrip("\n").split("\t")
        signature = [int(v) for v in values.split()]
        for key in lsh.band_keys(signature, bands, rows):
            print(f"{key}\t{window_id}")


if __name__ == "__main__":
    main()
