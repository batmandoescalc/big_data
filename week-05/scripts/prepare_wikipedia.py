#!/usr/bin/env python3
"""Stream Wikimedia XML dumps into nested, record-complete TSV samples."""

from __future__ import annotations

import argparse
import bz2
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
SIZE_RE = re.compile(r"^(\d+)(B|KiB|MiB|GiB)?$", re.IGNORECASE)
UNITS = {"b": 1, "kib": 1024, "mib": 1024**2, "gib": 1024**3}
PAGE_HEADER = "record_id\tdimension_key\tword_count\ttext_bytes\ttext\n"
DIMENSION_HEADER = "dimension_key\tcategory\n"


def parse_size(value: str) -> int:
    match = SIZE_RE.fullmatch(value.strip())
    if not match:
        raise argparse.ArgumentTypeError(f"invalid size: {value}")
    return int(match.group(1)) * UNITS[(match.group(2) or "B").lower()]


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def sanitize(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").replace("\t", " ")


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _direct(element, name):
    for child in element:
        if local_name(child.tag) == name:
            return child
    return None


def parse_page(element):
    page_id = _direct(element, "id")
    namespace = _direct(element, "ns")
    revision = _direct(element, "revision")
    text = _direct(revision, "text") if revision is not None else None
    if page_id is None or namespace is None or not page_id.text or namespace.text is None:
        return None
    body = sanitize(text.text or "") if text is not None else ""
    return (
        page_id.text.strip(),
        namespace.text.strip(),
        len(WORD_RE.findall(body)),
        len(body.encode("utf-8")),
        body,
    )


def iter_dump(path: Path, namespaces: dict[str, str], stats: dict[str, int]):
    opener = bz2.open if path.suffix.lower() == ".bz2" else open
    with opener(path, "rb") as stream:
        try:
            for event, element in ET.iterparse(stream, events=("end",)):
                name = local_name(element.tag)
                if name == "namespace" and "key" in element.attrib:
                    key = element.attrib["key"]
                    category = sanitize(element.text or "(main)") or "(main)"
                    if key in namespaces and namespaces[key] != category:
                        raise ValueError(f"conflicting namespace {key}: {namespaces[key]} / {category}")
                    namespaces[key] = category
                    element.clear()
                elif name == "page":
                    record = parse_page(element)
                    if record is None:
                        stats["malformed_pages"] += 1
                    else:
                        stats["pages_seen"] += 1
                        yield record
                    element.clear()
        except ET.ParseError as error:
            raise ValueError(f"malformed XML in {path}: {error}") from error


def prepare(sources, output_root: Path, targets, snapshot="unknown", source_urls=None):
    if output_root.exists():
        raise FileExistsError(f"output already exists: {output_root}")
    sources = [Path(source) for source in sources]
    targets = sorted(set(targets))
    if not sources or not targets or targets[0] <= 0:
        raise ValueError("at least one source and one positive target are required")
    output_root.mkdir(parents=True)
    source_urls = source_urls or [None] * len(sources)
    source_records = [
        {
            "path": source.name,
            "url": source_urls[index] if index < len(source_urls) else None,
            "compressed_bytes": source.stat().st_size,
            "sha256": hash_file(source),
        }
        for index, source in enumerate(sources)
    ]
    samples = []
    for target in targets:
        directory = output_root / f"sample-{target}"
        directory.mkdir()
        pages = directory / "pages.tsv"
        writer = pages.open("w", encoding="utf-8", newline="")
        writer.write(PAGE_HEADER)
        samples.append(
            {
                "target_bytes": target,
                "directory": directory,
                "pages": pages,
                "writer": writer,
                "rows": 0,
                "bytes": len(PAGE_HEADER.encode("utf-8")),
                "dimension_keys": set(),
                "complete": False,
            }
        )

    namespaces = {}
    stats = {"pages_seen": 0, "malformed_pages": 0}
    try:
        for source in sources:
            for page_id, namespace, words, text_bytes, body in iter_dump(source, namespaces, stats):
                line = f"{page_id}\t{namespace}\t{words}\t{text_bytes}\t{body}\n"
                encoded_bytes = len(line.encode("utf-8"))
                for sample in samples:
                    if sample["complete"]:
                        continue
                    sample["writer"].write(line)
                    sample["rows"] += 1
                    sample["bytes"] += encoded_bytes
                    sample["dimension_keys"].add(namespace)
                    if sample["bytes"] >= sample["target_bytes"]:
                        sample["complete"] = True
                        sample["writer"].close()
                if all(sample["complete"] for sample in samples):
                    break
            if all(sample["complete"] for sample in samples):
                break
    finally:
        for sample in samples:
            if not sample["writer"].closed:
                sample["writer"].close()

    if not namespaces:
        raise ValueError("dump did not contain namespace metadata")
    generated = datetime.now(timezone.utc).isoformat()
    for sample in samples:
        dimensions = sample["directory"] / "namespaces.tsv"
        with dimensions.open("w", encoding="utf-8", newline="") as output:
            output.write(DIMENSION_HEADER)
            for key in sorted(namespaces, key=lambda value: int(value)):
                output.write(f"{key}\t{namespaces[key]}\n")
        manifest = {
            "schema_version": 1,
            "dataset_id": f"enwiki-{snapshot}-{sample['target_bytes']}",
            "snapshot": snapshot,
            "target_bytes": sample["target_bytes"],
            "actual_bytes": sample["bytes"],
            "page_rows": sample["rows"],
            "dimension_rows": len(namespaces),
            "output_rows": len(sample["dimension_keys"]),
            "complete": sample["complete"],
            "generated_utc": generated,
            "malformed_pages": stats["malformed_pages"],
            "sources": source_records,
        }
        (sample["directory"] / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    return [sample["directory"] for sample in samples]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", type=Path, default=[])
    parser.add_argument(
        "--source-manifest",
        type=Path,
        help="source-manifest.json written by fetch_wikipedia.py",
    )
    parser.add_argument("--source-url", action="append", default=[])
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument(
        "--target",
        action="append",
        type=parse_size,
        required=True,
        help="nested sample target such as 2MiB, 128MiB, 1GiB",
    )
    args = parser.parse_args()
    sources = list(args.source)
    source_urls = list(args.source_url)
    if args.source_manifest:
        metadata = json.loads(args.source_manifest.read_text(encoding="utf-8"))
        for part in metadata["parts"]:
            sources.append(args.source_manifest.parent / part["name"])
            source_urls.append(part["url"])
    if not sources:
        parser.error("at least one --source or --source-manifest is required")
    prepare(sources, args.output_root, args.target, args.snapshot, source_urls)


if __name__ == "__main__":
    main()
