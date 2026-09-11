#!/usr/bin/env python3
"""Download three NASA Apollo 11 transcripts and extract visible text.

Uses only the Python standard library. Originals and provenance are retained;
punctuation, timestamps, speaker labels, and OCR errors are not corrected.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.request import Request, urlopen


BASE = "https://www.nasa.gov/wp-content/uploads/static/history/alsj/a11/"
INDEX = BASE + "a11trans.html"
SOURCES = (
    ("air-to-ground", "Technical air-to-ground voice transcript", "a11transcript_tec.html"),
    ("public-commentary", "Public Affairs Office spacecraft commentary", "a11transcript_pao.html"),
    ("onboard-voice", "Command module onboard voice transcript", "a11transscript_cm.html"),
)


class VisibleText(HTMLParser):
    """Keep body text and separate block elements without joining adjacent words."""
    BLOCKS = {"br", "hr", "p", "div", "tr", "li", "pre", "table", "h1", "h2", "h3", "h4"}
    HIDDEN = {"script", "style", "noscript", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_body = False
        self.hidden_depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.in_body = True
        if not self.in_body:
            return
        if tag in self.HIDDEN:
            self.hidden_depth += 1
        if not self.hidden_depth:
            if tag in self.BLOCKS:
                self.parts.append("\n")
            elif tag in {"td", "th"}:
                self.parts.append(" ")

    def handle_endtag(self, tag):
        if not self.in_body:
            return
        if tag in self.HIDDEN:
            self.hidden_depth = max(0, self.hidden_depth - 1)
        if not self.hidden_depth:
            if tag in self.BLOCKS:
                self.parts.append("\n")
            elif tag in {"td", "th"}:
                self.parts.append(" ")
        if tag == "body":
            self.in_body = False

    def handle_data(self, data):
        if self.in_body and not self.hidden_depth:
            self.parts.append(data)

    def text(self):
        lines = (" ".join(line.split()) for line in "".join(self.parts).splitlines())
        return "\n".join(line for line in lines if line) + "\n"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def decode_source(raw, declared):
    try:
        return raw.decode(declared), declared
    except UnicodeDecodeError:
        if declared.lower().replace("_", "-") not in {"utf-8", "utf8"}:
            raise
        # These archived pages can be served as UTF-8 despite legacy bytes.
        # Use a strict, reversible decoding and record it in the manifest.
        return raw.decode("windows-1252"), "windows-1252"


def fetch(output):
    if output.exists():
        raise ValueError(f"Output already exists: {output}. Use a new snapshot directory.")
    artifacts = {}
    records = []
    for slug, title, filename in SOURCES:
        url = BASE + filename
        request = Request(url, headers={"User-Agent": "HadoopStudyDataset/1.0 (small educational download)"})
        with urlopen(request, timeout=30) as response:
            if response.headers.get_content_type() != "text/html":
                raise ValueError(f"Expected HTML from {url}")
            raw = response.read(10_000_001)
            if len(raw) > 10_000_000:
                raise ValueError(f"Unexpectedly large response from {url}")
            declared_encoding = response.headers.get_content_charset() or "utf-8"
            final_url = response.url
        parser = VisibleText()
        source_text, encoding = decode_source(raw, declared_encoding)
        parser.feed(source_text)
        parser.close()
        text = parser.text()
        if len(text) < 10_000 or "apollo" not in text.lower():
            raise ValueError(f"Response does not look like the expected transcript: {url}")
        plain = text.encode("utf-8")
        raw_path = f"raw/{slug}.html"
        text_path = f"text/{slug}.txt"
        artifacts[raw_path] = raw
        artifacts[text_path] = plain
        records.append({
            "id": slug, "title": title, "url": url, "resolved_url": final_url,
            "retrieved_utc": datetime.now(timezone.utc).isoformat(),
            "declared_encoding": declared_encoding, "source_encoding": encoding,
            "raw_path": raw_path, "raw_bytes": len(raw), "raw_sha256": sha256(raw),
            "text_path": text_path, "text_bytes": len(plain), "text_sha256": sha256(plain),
            "nonempty_lines": len(text.splitlines()),
            "whitespace_tokens": len(text.split()),
        })
        print(f"Fetched {slug}: {len(plain):,} text bytes; decoded as {encoding}", flush=True)
    manifest = {
        "dataset": "Apollo 11 mission transcripts", "source_index": INDEX,
        "rights_note": "NASA's index states that no copyright is asserted for these raw transcripts.",
        "processing": "Extract HTML body text; remove scripts/styles and markup; normalize whitespace; write UTF-8. Retain timestamps, speaker labels, headers, and uncorrected OCR wording.",
        "sources": records,
        "total_text_bytes": sum(r["text_bytes"] for r in records),
        "total_whitespace_tokens": sum(r["whitespace_tokens"] for r in records),
    }
    # All downloads and validation finish before writing the snapshot.
    output.mkdir(parents=True, exist_ok=False)
    for relative, data in artifacts.items():
        target = output / relative
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(data)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(records)} transcripts, {manifest['total_text_bytes']:,} text bytes, "
          f"{manifest['total_whitespace_tokens']:,} whitespace tokens to {output}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=Path, default=Path("data/apollo11"))
    fetch(cli.parse_args().output)
