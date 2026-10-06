#!/usr/bin/env python3
"""Sum count, word, and byte measures for each sorted category key."""

import sys


current = None
counts = words = text_bytes = 0


def emit():
    if current is not None:
        print(current, counts, words, text_bytes, sep="\t")


for line_number, raw_line in enumerate(sys.stdin, start=1):
    fields = raw_line.rstrip("\n").split("\t")
    if len(fields) != 4:
        print(f"invalid aggregate row at input line {line_number}", file=sys.stderr)
        raise SystemExit(1)
    category, count, word_count, byte_count = fields
    try:
        values = (int(count), int(word_count), int(byte_count))
    except ValueError:
        print(f"invalid aggregate measures at input line {line_number}", file=sys.stderr)
        raise SystemExit(1)
    if category != current:
        emit()
        current = category
        counts = words = text_bytes = 0
    counts += values[0]
    words += values[1]
    text_bytes += values[2]

emit()
