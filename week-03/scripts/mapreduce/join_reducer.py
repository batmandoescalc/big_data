#!/usr/bin/env python3
"""Natural-join utterances with speaker metadata after Hadoop's sort."""

import sys


current_code = None
category = None
pending = []


def emit(values):
    utterance_id, mission_time, word_count, text = values
    print(
        utterance_id,
        mission_time,
        current_code,
        category,
        word_count,
        text,
        sep="\t",
    )


def finish_group():
    if not pending:
        return
    if category is None:
        print(
            f"reporter:counter:Week3,Unmatched utterances,{len(pending)}",
            file=sys.stderr,
        )
        return
    for values in pending:
        emit(values)

for raw_line in sys.stdin:
    fields = raw_line.rstrip("\n").split("\t")
    if len(fields) < 3:
        print("Invalid mapped join record", file=sys.stderr)
        raise SystemExit(1)
    speaker_code, relation, *values = fields
    if speaker_code != current_code:
        finish_group()
        current_code = speaker_code
        category = None
        pending = []
    if relation == "S":
        if len(values) != 2 or category is not None:
            print(f"Invalid or duplicate speaker record: {speaker_code}", file=sys.stderr)
            raise SystemExit(1)
        category = values[0]
        for utterance in pending:
            emit(utterance)
        pending = []
    elif relation == "U":
        if len(values) != 4:
            print(f"Invalid utterance record: {speaker_code}", file=sys.stderr)
            raise SystemExit(1)
        if category is None:
            pending.append(values)
        else:
            emit(values)
    else:
        print(f"Unknown relation tag: {relation}", file=sys.stderr)
        raise SystemExit(1)

finish_group()
