#!/usr/bin/env python3
"""Download one day of hourly Wikipedia pageview dumps, politely and resumably.

Source: https://dumps.wikimedia.org/other/pageviews/ (Wikimedia Analytics,
CC0 public domain dedication). One gzipped file per hour.

- Files are fetched one at a time, never in parallel.
- A file whose size already equals the server's Content-Length is skipped.
- A partial file is resumed with an HTTP Range request when the server allows
  it; otherwise it is downloaded again from the start.
- A manifest JSON (url, bytes, sha256 per file) is written next to the data.
- ``--dry-run`` only sends HEAD requests and prints URLs and total bytes.

Usage:
    python3 week-08/scripts/download_pageviews.py --dry-run
    python3 week-08/scripts/download_pageviews.py \\
        --out-dir data/week-08/pageviews
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

BASE_URL = "https://dumps.wikimedia.org/other/pageviews"
USER_AGENT = "big_data-coursework/1.0"
CHUNK = 1 << 20


def parse_hours(text: str) -> list[int]:
    """Turn '00-23', '12' or '0,5,7-9' into a sorted list of hours."""
    hours = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = (int(x) for x in part.split("-", 1))
            hours.update(range(start, end + 1))
        else:
            hours.add(int(part))
    if not hours or min(hours) < 0 or max(hours) > 23:
        raise ValueError(f"hours must be within 00-23: {text!r}")
    return sorted(hours)


def file_name(day: str, hour: int) -> str:
    """Return the dump file name for a day (YYYYMMDD) and hour."""
    return f"pageviews-{day}-{hour:02d}0000.gz"


def file_url(day: str, hour: int) -> str:
    """Return the full dump URL for a day (YYYYMMDD) and hour."""
    return f"{BASE_URL}/{day[:4]}/{day[:4]}-{day[4:6]}/{file_name(day, hour)}"


def _request(url: str, method: str = "GET", headers=None):
    req = urllib.request.Request(url, method=method,
                                 headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(req, timeout=60)


def remote_size(url: str) -> int:
    """Return the server's Content-Length for a URL via HEAD."""
    with _request(url, "HEAD") as response:
        length = response.headers.get("Content-Length")
    if length is None:
        raise RuntimeError(f"no Content-Length for {url}")
    return int(length)


def sha256_of(path: Path) -> str:
    """Return the hex SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path, expected: int, retries: int = 3) -> None:
    """Fetch url into target until its size equals expected, resuming if possible."""
    for attempt in range(1, retries + 1):
        have = target.stat().st_size if target.exists() else 0
        if have > expected:
            target.unlink()
            have = 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with _request(url, headers=headers) as response:
                resumed = have and response.status == 206
                mode = "ab" if resumed else "wb"
                with target.open(mode) as handle:
                    for chunk in iter(lambda: response.read(CHUNK), b""):
                        handle.write(chunk)
        except (urllib.error.URLError, OSError) as error:
            print(f"  attempt {attempt} failed: {error}", file=sys.stderr)
            time.sleep(5 * attempt)
            continue
        if target.stat().st_size == expected:
            return
        print(f"  attempt {attempt}: size {target.stat().st_size} != {expected}",
              file=sys.stderr)
    raise RuntimeError(f"could not download {url} after {retries} attempts")


def main(argv=None) -> int:
    """Parse arguments, then HEAD (dry run) or download every requested hour."""
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--day", default="20261027", help="YYYYMMDD (default 20261027)")
    parser.add_argument("--hours", default="00-23", help="e.g. 00-23 or 12 (default 00-23)")
    parser.add_argument("--out-dir", type=Path, default=Path("data/week-08/pageviews"))
    parser.add_argument("--dry-run", action="store_true",
                        help="print URLs and total bytes via HEAD; download nothing")
    args = parser.parse_args(argv)

    hours = parse_hours(args.hours)
    plan = []
    for hour in hours:
        url = file_url(args.day, hour)
        size = remote_size(url)
        plan.append((hour, url, size))
        if args.dry_run:
            print(f"{url}  {size:,} bytes")
    total = sum(size for _, _, size in plan)
    print(f"{len(plan)} files, {total:,} bytes gzipped ({total / 1e9:.3f} GB)")
    if args.dry_run:
        return 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out_dir / "manifest.json"
    old = {}
    if manifest_path.exists():
        old = {entry["file"]: entry
               for entry in json.loads(manifest_path.read_text())["files"]}
    entries = dict(old)  # keep entries for hours not requested this time
    for hour, url, size in plan:
        name = file_name(args.day, hour)
        target = args.out_dir / name
        if target.exists() and target.stat().st_size == size:
            print(f"skip  {name} (complete, {size:,} bytes)")
        else:
            print(f"fetch {name} ({size:,} bytes)", flush=True)
            started = time.perf_counter()
            download(url, target, size)
            seconds = time.perf_counter() - started
            print(f"  done in {seconds:.1f} s ({size / 1e6 / max(seconds, 1e-9):.1f} MB/s)")
            old.pop(name, None)
        cached = old.get(name)
        if cached and cached.get("bytes") == size:
            digest = cached["sha256"]
        else:
            digest = sha256_of(target)
        entries[name] = {"file": name, "url": url, "bytes": size, "sha256": digest}
        listed = [entries[key] for key in sorted(entries)]
        # Rewrite after every file so an interrupted run keeps its progress.
        manifest = {"source": BASE_URL, "license": "CC0 1.0 (Wikimedia Analytics datasets)",
                    "day": args.day, "user_agent": USER_AGENT,
                    "total_bytes": sum(entry["bytes"] for entry in listed),
                    "files": listed}
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
