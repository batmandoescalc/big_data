#!/usr/bin/env python3
"""Convert the Apollo 11 air-to-ground transcript into two TSV relations."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import re


HEADER_RE = re.compile(
    r"^(?P<day>\d{2})\s+(?P<hour>\d{2})\s+(?P<minute>\d{2})\s+"
    r"(?P<second>\d{2})\s+(?P<speaker>[A-Z][A-Z0-9/-]*)"
    r"(?:\s+(?P<inline>.*))?$"
)
TIMESTAMP_LIKE_RE = re.compile(r"^(?:[0-9O]{2}\s+){3}[0-9O]{2}\s+")
WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)*")

SPEAKERS = (
    ("CDR", "crew", "Commander, Neil A. Armstrong"),
    ("CMP", "crew", "Command module pilot, Michael Collins"),
    ("LMP", "crew", "Lunar module pilot, Edwin E. Aldrin Jr."),
    ("SC", "crew", "Unidentified crewmember"),
    ("MS", "crew", "Multiple simultaneous speakers"),
    ("CC", "mission-control", "Capsule communicator"),
    ("F", "mission-control", "Flight director"),
    ("CT", "remote-site", "Communications technician"),
    ("MSFN", "remote-site", "Manned Space Flight Network"),
    ("HORNET", "recovery", "USS Hornet"),
    ("R", "recovery", "Recovery helicopter"),
    ("AB", "recovery", "Air boss"),
)

METADATA_RE = re.compile(
    r"^(?:\* \* \*|NOTE|END OF TAPE|INTRODUCTION|"
    r"APOLLO 11 AIR-TO-GROUND VOICE TRANSCRIPTION|"
    r"THE FOLLOWING IS A MESSAGE.*|"
    r"\*{3} Three asterisks.*|"
    r"\(GOSS NET 1\).*|"
    r"[A-Z][A-Z .'-]+ \(REV\s*\d+\))$"
)


def sanitize(value: str) -> str:
    """Make a value safe for one physical TSV record."""
    return " ".join(value.replace("\t", " ").split())


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text.lower().replace("’", "'")))


def parse_transcript(text: str, source_id: str = "air-to-ground"):
    """Return parsed utterances plus diagnostics for ignored malformed records."""
    utterances = []
    malformed_headers = []
    current = None

    def finish_current():
        nonlocal current
        if current is None:
            return
        spoken = sanitize(" ".join(current.pop("parts")))
        if spoken:
            current["text"] = spoken
            current["word_count"] = count_words(spoken)
            utterances.append(current)
        current = None

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = sanitize(raw_line)
        if not line:
            continue
        match = HEADER_RE.match(line)
        if match:
            finish_current()
            values = match.groupdict()
            inline = values.get("inline") or ""
            # Parenthetical role annotations such as "(EVA)" are metadata,
            # not spoken transcript text.
            if re.fullmatch(r"\([^)]+\)", inline):
                inline = ""
            current = {
                "mission_time": ":".join(
                    values[name] for name in ("day", "hour", "minute", "second")
                ),
                "speaker_code": values["speaker"],
                "parts": [inline] if inline else [],
                "source_line": line_number,
            }
            continue
        if TIMESTAMP_LIKE_RE.match(line):
            finish_current()
            malformed_headers.append({"line": line_number, "text": line})
            continue
        if METADATA_RE.match(line):
            continue
        if current is not None:
            current["parts"].append(line)

    finish_current()
    for number, record in enumerate(utterances, start=1):
        record["utterance_id"] = f"{source_id}-{number:06d}"
    return utterances, malformed_headers


def write_tsv(path: Path, fieldnames, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fieldnames, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def prepare(input_path: Path, output_dir: Path):
    if output_dir.exists():
        raise ValueError(f"Output already exists: {output_dir}")
    text = input_path.read_text(encoding="utf-8")
    utterances, malformed = parse_transcript(text)
    speaker_codes = {row[0] for row in SPEAKERS}
    observed_codes = {row["speaker_code"] for row in utterances}
    unknown_codes = sorted(observed_codes - speaker_codes)
    if not utterances:
        raise ValueError("No transcript utterances were parsed")

    output_dir.mkdir(parents=True)
    write_tsv(
        output_dir / "utterances.tsv",
        ("record_type", "utterance_id", "mission_time", "speaker_code", "word_count", "text"),
        (
            {
                "record_type": "U",
                "utterance_id": row["utterance_id"],
                "mission_time": row["mission_time"],
                "speaker_code": row["speaker_code"],
                "word_count": row["word_count"],
                "text": row["text"],
            }
            for row in utterances
        ),
    )
    write_tsv(
        output_dir / "speakers.tsv",
        ("record_type", "speaker_code", "category", "description"),
        (
            {
                "record_type": "S",
                "speaker_code": code,
                "category": category,
                "description": description,
            }
            for code, category, description in SPEAKERS
        ),
    )
    manifest = {
        "source": str(input_path),
        "utterance_rows": len(utterances),
        "speaker_rows": len(SPEAKERS),
        "matched_utterance_rows": sum(
            row["speaker_code"] in speaker_codes for row in utterances
        ),
        "malformed_headers": malformed,
        "unknown_speaker_codes": unknown_codes,
        "word_count_rule": "Lowercase English letters with internal apostrophes",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest = prepare(args.input, args.output_dir)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
