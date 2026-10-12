#!/usr/bin/env python3
"""Adapt the Week 3 Apollo relations to the generic Week 5 benchmark schema."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def convert(utterances: Path, speakers: Path, output: Path):
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    output.mkdir(parents=True)
    known_speakers = {}
    with speakers.open("r", encoding="utf-8", newline="") as source, (
        output / "namespaces.tsv"
    ).open("w", encoding="utf-8", newline="") as target:
        reader = csv.DictReader(source, delimiter="\t")
        target.write("dimension_key\tcategory\n")
        for row in reader:
            known_speakers[row["speaker_code"]] = row["category"]
            target.write(f"{row['speaker_code']}\t{row['category']}\n")
    input_rows = 0
    matched_rows = 0
    unmatched_codes = set()
    with utterances.open("r", encoding="utf-8", newline="") as source, (
        output / "pages.tsv"
    ).open("w", encoding="utf-8", newline="") as target:
        reader = csv.DictReader(source, delimiter="\t")
        target.write("record_id\tdimension_key\tword_count\ttext_bytes\ttext\n")
        for row in reader:
            input_rows += 1
            if row["speaker_code"] not in known_speakers:
                unmatched_codes.add(row["speaker_code"])
                continue
            text = row["text"].replace("\t", " ").replace("\r", " ").replace("\n", " ")
            target.write(
                f"{row['utterance_id']}\t{row['speaker_code']}\t{row['word_count']}\t"
                f"{len(text.encode('utf-8'))}\t{text}\n"
            )
            matched_rows += 1
    summary = {
        "input_rows": input_rows,
        "matched_rows": matched_rows,
        "unmatched_rows": input_rows - matched_rows,
        "unmatched_speaker_codes": sorted(unmatched_codes),
        "dimension_rows": len(known_speakers),
    }
    (output / "manifest.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("utterances", type=Path)
    parser.add_argument("speakers", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(convert(args.utterances, args.speakers, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
