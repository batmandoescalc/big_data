#!/usr/bin/env python3
"""Compute COUNT(*) and SUM(word_count) for each category."""

import sys


current_category = None
utterance_count = 0
total_words = 0


def emit():
    if current_category is not None:
        print(current_category, utterance_count, total_words, sep="\t")


for raw_line in sys.stdin:
    fields = raw_line.rstrip("\n").split("\t")
    if len(fields) != 3:
        print("Invalid aggregate input", file=sys.stderr)
        raise SystemExit(1)
    category, row_count, word_count = fields
    if category != current_category:
        emit()
        current_category = category
        utterance_count = 0
        total_words = 0
    utterance_count += int(row_count)
    total_words += int(word_count)

emit()
