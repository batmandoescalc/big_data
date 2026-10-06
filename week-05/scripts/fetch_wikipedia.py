#!/usr/bin/env python3
"""Select and download verified split files from a pinned Wikimedia dump run."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

from prepare_wikipedia import parse_size


PART_RE = re.compile(r"pages-articles-multistream(\d+)\.xml-p\d+p\d+\.bz2$")
USER_AGENT = "CSE4099-big-data-study/1.0 (+https://github.com/batmandoescalc/big_data)"


def open_url(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}))


def select_parts(status, max_compressed_bytes):
    candidates = []
    for job in status.get("jobs", {}).values():
        for name, metadata in (job.get("files") or {}).items():
            match = PART_RE.search(name)
            if not match or not metadata.get("url") or not metadata.get("size"):
                continue
            candidates.append((int(match.group(1)), name, metadata))
    selected = []
    total = 0
    for _, name, metadata in sorted(candidates):
        size = int(metadata["size"])
        if selected and total + size > max_compressed_bytes:
            break
        selected.append(
            {
                "name": name,
                "url": urllib.parse.urljoin("https://dumps.wikimedia.org/", metadata["url"]),
                "bytes": size,
                "sha1": metadata.get("sha1"),
            }
        )
        total += size
    if not selected:
        raise ValueError("dump status contained no matching article multistream parts")
    return selected


def sha1(path):
    digest = hashlib.sha1()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(part, output_dir):
    destination = output_dir / part["name"]
    if destination.exists():
        if destination.stat().st_size == part["bytes"] and (
            not part["sha1"] or sha1(destination) == part["sha1"]
        ):
            return destination
        raise ValueError(f"existing file does not match manifest: {destination}")
    temporary = destination.with_suffix(destination.suffix + ".part")
    with open_url(part["url"]) as response, temporary.open("wb") as target:
        while chunk := response.read(1024 * 1024):
            target.write(chunk)
    if temporary.stat().st_size != part["bytes"]:
        raise ValueError(f"download size mismatch: {part['name']}")
    if part["sha1"] and sha1(temporary) != part["sha1"]:
        raise ValueError(f"download checksum mismatch: {part['name']}")
    temporary.replace(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-url", required=True, help="pinned dumpstatus.json URL")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-compressed", type=parse_size, default=parse_size("30GiB"))
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args()
    with open_url(args.status_url) as response:
        status = json.load(response)
    parts = select_parts(status, args.max_compressed)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status_url": args.status_url,
        "selected_compressed_bytes": sum(part["bytes"] for part in parts),
        "parts": parts,
    }
    (args.output_dir / "source-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    if not args.manifest_only:
        for part in parts:
            print(f"Downloading {part['name']} ({part['bytes']} bytes)", flush=True)
            download(part, args.output_dir)


if __name__ == "__main__":
    main()
