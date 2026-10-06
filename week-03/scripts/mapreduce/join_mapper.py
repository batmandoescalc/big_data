#!/usr/bin/env python3
"""Tag both relations and key them by speaker_code for a reduce-side join."""

import sys


for raw_line in sys.stdin:
    line = raw_line.rstrip("\n")
    if not line or line.startswith("record_type\t"):
        continue
    fields = line.split("\t")
    relation = fields[0]
    if relation == "S" and len(fields) == 4:
        _, speaker_code, category, description = fields
        print(speaker_code, "S", category, description, sep="\t")
    elif relation == "U" and len(fields) == 6:
        _, utterance_id, mission_time, speaker_code, word_count, text = fields
        int(word_count)
        print(
            speaker_code,
            "U",
            utterance_id,
            mission_time,
            word_count,
            text,
            sep="\t",
        )
    else:
        print("Invalid input record: " + line, file=sys.stderr)
        raise SystemExit(1)
