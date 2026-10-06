#!/usr/bin/env python3
"""Key joined utterances by speaker category for aggregation."""

import sys


for raw_line in sys.stdin:
    fields = raw_line.rstrip("\n").split("\t")
    if len(fields) != 6:
        print("Invalid joined record", file=sys.stderr)
        raise SystemExit(1)
    _, _, _, category, word_count, _ = fields
    int(word_count)
    print(category, 1, word_count, sep="\t")
