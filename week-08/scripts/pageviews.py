"""Run the four Week 7 stream sketches over real Wikipedia pageview dumps.

Each hourly dump line is ``wiki_code page_title views 0``.  The stream key is
``wiki_code + " " + page_title``, and every line is hashed exactly once with
64-bit BLAKE2b.  All four sketches take what they need from that one hash:

- Bloom filter: double hashing, positions ``a + i*b`` (``a`` = low 32 bits,
  ``b`` = high 32 bits, forced odd).
- Flajolet-Martin: the low 12 bits pick one of 4,096 registers (stochastic
  averaging); the trailing zeros of the remaining 52 bits are the book's R.
- AMS: the hash identifies the sampled key; the line's view count says how
  many stream arrivals the line stands for.
- DGIM: does not hash; bit = 1 when a line's views reach a threshold.

The exact answers need every distinct key, which does not fit comfortably in
Python memory for a whole day (about 60 million keys).  The exact side
therefore writes (hash, views) pairs to 64 partition files on disk by the top
6 hash bits, then aggregates one partition at a time.  Two different keys
sharing a 64-bit hash would merge; with about 6e7 keys the chance of even
one such collision is about n^2 / 2^65, roughly 1e-4, so it is ignored.

Python standard library only (the course cluster runs Python 3.9).
"""

from __future__ import annotations

from array import array
from bisect import bisect_right
from collections import deque
import gzip
import hashlib
import heapq
import math
from pathlib import Path
import re
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dgim_reduced_error import DGIMReduced  # noqa: E402
from dgim_study import week7_original_estimate  # noqa: E402

FILE_PATTERN = re.compile(r"^pageviews-(\d{8})-(\d{2})0000\.gz$")
_MASKS = tuple(1 << bit for bit in range(8))
_U53 = float(1 << 53)


def key_hash(key: bytes) -> int:
    """Return the one 64-bit hash every sketch shares for a stream key."""
    return int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "little")


def parse_line(line: bytes):
    """Return (key_bytes, views) for a valid dump line, or None if malformed."""
    parts = line.rsplit(b" ", 2)
    if len(parts) != 3 or not parts[1].isdigit() or b" " not in parts[0]:
        return None
    return parts[0], int(parts[1])


def _round(value, digits=4):
    return None if value is None else round(value, digits)


def percent_error(estimate, exact):
    """Absolute percentage error, with 0 vs 0 counted as exact."""
    if exact == 0:
        return 0.0 if estimate == 0 else None  # undefined; JSON null
    return abs(estimate - exact) / exact * 100.0


# --------------------------------------------------------------------------
# Bloom filter driven by one 64-bit hash (Kirsch-Mitzenmacher double hashing)
# --------------------------------------------------------------------------

class HashedBloom:
    """Bloom filter whose k positions all come from one 64-bit hash."""

    def __init__(self, bits: int, hashes: int):
        if bits < 8 or hashes < 1:
            raise ValueError("need at least 8 bits and 1 hash")
        self.bits = bits
        self.hashes = hashes
        self.data = bytearray((bits + 7) // 8)
        self.inserted = 0

    @classmethod
    def for_capacity(cls, capacity: int, target_fp: float) -> "HashedBloom":
        """Size the filter for ``capacity`` keys at false-positive rate ``target_fp``."""
        capacity = max(1, capacity)
        bits = max(8, math.ceil(-capacity * math.log(target_fp) / (math.log(2) ** 2)))
        hashes = max(1, round(bits / capacity * math.log(2)))
        return cls(bits, hashes)

    def positions(self, h: int):
        """Return the k bit positions for hash ``h``: (a + i*b) mod bits."""
        a, b = h & 0xFFFFFFFF, (h >> 32) | 1
        return [(a + i * b) % self.bits for i in range(self.hashes)]

    def add_hash(self, h: int) -> None:
        """Insert one key, given its 64-bit hash."""
        data = self.data
        for p in self.positions(h):
            data[p >> 3] |= _MASKS[p & 7]
        self.inserted += 1

    def contains_hash(self, h: int) -> bool:
        """Return True if the key may have been inserted (never False for an inserted key)."""
        data = self.data
        return all(data[p >> 3] & _MASKS[p & 7] for p in self.positions(h))

    def theoretical_fp(self, inserted: int) -> float:
        """Textbook false-positive rate (1 - e^(-kn/m))^k for ``inserted`` keys."""
        return (1.0 - math.exp(-self.hashes * inserted / self.bits)) ** self.hashes

    @property
    def memory_bytes(self) -> int:
        """Bytes in the bit array."""
        return len(self.data)


# --------------------------------------------------------------------------
# Flajolet-Martin with stochastic averaging
# --------------------------------------------------------------------------

class HashedFM:
    """FM distinct counter: low hash bits pick a register, the rest give R.

    Each register stores rank = R + 1, where R is the number of trailing zero
    bits (0 means "register never touched").  Registers are combined with the
    harmonic mean and HyperLogLog's bias constant, the standard refinement of
    the book's "combine many FM estimates" step when each key updates only
    one register instead of all of them.
    """

    def __init__(self, register_bits: int = 12):
        if not 4 <= register_bits <= 20:
            raise ValueError("register_bits must be between 4 and 20")
        self.register_bits = register_bits
        self.m = 1 << register_bits
        self.registers = bytearray(self.m)

    def rank(self, h: int):
        """Return (register index, R + 1) for one 64-bit hash."""
        rest = h >> self.register_bits
        rank = (rest & -rest).bit_length() if rest else 64 - self.register_bits + 1
        return h & (self.m - 1), rank

    def add_hash(self, h: int) -> None:
        """Record one key, given its 64-bit hash."""
        index, rank = self.rank(h)
        if rank > self.registers[index]:
            self.registers[index] = rank

    def estimate(self) -> float:
        """Harmonic-mean FM estimate, with linear counting when many registers are empty."""
        m = self.m
        alpha = 0.7213 / (1 + 1.079 / m)
        raw = alpha * m * m / sum(2.0 ** -r for r in self.registers)
        empty = self.registers.count(0)
        if raw <= 2.5 * m and empty:
            return m * math.log(m / empty)
        return raw

    @property
    def memory_bytes(self) -> int:
        """One byte per register."""
        return self.m


# --------------------------------------------------------------------------
# AMS second moment on a weighted stream, without expanding it
# --------------------------------------------------------------------------

class WeightedAMS:
    """AMS F2 estimators where one line with ``views = c`` is c stream arrivals.

    The book's AMS picks a uniformly random arrival position for each
    variable (reservoir sampling) and counts how often that key occurs from
    there to the end.  Instead of flipping a coin per arrival, each variable
    keeps the arrival index T of its next replacement.  After a replacement
    at T, the next one is at floor(T / U) + 1 for U uniform in (0, 1], since
    the chance of surviving to t is T / t.  A line covering arrivals
    n+1 .. n+c replaces every variable whose T falls inside it, and the new
    count is the arrivals left in that line from T on (n + c - T + 1).  Later
    lines of the same key add their full c.  This gives the same distribution
    as running week 7's AMSSecondMoment on the expanded stream.
    """

    def __init__(self, variables: int = 4096, seed: int = 4099, groups: int = 8):
        if variables < 1 or groups < 1 or variables % groups:
            raise ValueError("variables must be a positive multiple of groups")
        self.seed = seed
        self.groups = groups
        self.keys = [None] * variables
        self.counts = [0] * variables
        self.draws = [0] * variables
        self.holders: dict = {}
        self.length = 0
        self.heap = [(1, index) for index in range(variables)]  # first arrival always samples
        heapq.heapify(self.heap)
        self.next_replacement = 1

    def uniform(self, variable: int, draw: int) -> float:
        """Repeatable U in (0, 1] for one variable's draw-th replacement."""
        payload = f"{self.seed}|{variable}|{draw}".encode()
        bits = int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "little") >> 11
        return (bits + 1) / _U53

    def add(self, key, count: int) -> None:
        """Process one line: key ``key`` arriving ``count`` times in a row."""
        if count <= 0:
            return
        held = self.holders.get(key)
        if held:
            counts = self.counts
            for index in held:
                counts[index] += count
        self.length += count
        if self.length >= self.next_replacement:
            self._replace(key)

    def _replace(self, key) -> None:
        end, heap = self.length, self.heap
        while heap[0][0] <= end:
            position, index = heapq.heappop(heap)
            old = self.keys[index]
            if old is not None and old != key:
                holders = self.holders[old]
                holders.discard(index)
                if not holders:
                    del self.holders[old]
            self.keys[index] = key
            self.holders.setdefault(key, set()).add(index)
            self.counts[index] = end - position + 1
            self.draws[index] += 1
            following = math.floor(position / self.uniform(index, self.draws[index])) + 1
            heapq.heappush(heap, (following, index))
        self.next_replacement = heap[0][0]

    def variable_estimates(self):
        """Return each variable's estimate n * (2 * count - 1)."""
        return [self.length * (2 * count - 1) for count in self.counts]

    def mean_estimate(self) -> float:
        """Mean of all variables (unbiased)."""
        values = self.variable_estimates()
        return sum(values) / len(values) if self.length else 0.0

    def estimate(self) -> float:
        """Book's combination: median of the means of equal groups."""
        if not self.length:
            return 0.0
        values = self.variable_estimates()
        size = len(values) // self.groups
        means = sorted(sum(values[i:i + size]) / size for i in range(0, len(values), size))
        middle = len(means) // 2
        return means[middle] if len(means) % 2 else (means[middle - 1] + means[middle]) / 2

    @property
    def memory_bytes(self) -> int:
        """Logical size: an 8-byte key hash and an 8-byte count per variable."""
        return len(self.counts) * 16


# --------------------------------------------------------------------------
# Running everything over a set of hourly files
# --------------------------------------------------------------------------

def find_files(input_dir: Path, hours) -> list:
    """Return [(hour, path)] for dump files in input_dir whose hour is wanted."""
    found = []
    for path in sorted(Path(input_dir).iterdir()):
        match = FILE_PATTERN.match(path.name)
        if match and int(match.group(2)) in hours:
            found.append((int(match.group(2)), path))
    if not found:
        raise FileNotFoundError(f"no pageviews-*-HH0000.gz files for hours {hours} in {input_dir}")
    days = {FILE_PATTERN.match(path.name).group(1) for _, path in found}
    if len(days) != 1 or len(found) != len({hour for hour, _ in found}):
        raise ValueError("expected exactly one file per hour from a single day")
    return found


class _Partitions:
    """Spill (hash, value) pairs to 64 files by the top 6 hash bits."""

    PARTS = 64

    def __init__(self, folder: Path, name: str):
        self.folder, self.name = folder, name
        self.hashes = [array("Q") for _ in range(self.PARTS)]
        self.values = [array("q") for _ in range(self.PARTS)]

    def path(self, part: int, kind: str) -> Path:
        return self.folder / f"{self.name}-{part:02d}.{kind}"

    def flush(self) -> None:
        for part in range(self.PARTS):
            if self.hashes[part]:
                with self.path(part, "h").open("ab") as handle:
                    self.hashes[part].tofile(handle)
                with self.path(part, "v").open("ab") as handle:
                    self.values[part].tofile(handle)
                self.hashes[part] = array("Q")
                self.values[part] = array("q")

    def load(self, part: int):
        hashes, values = array("Q"), array("q")
        for target, kind in ((hashes, "h"), (values, "v")):
            path = self.path(part, kind)
            if path.exists():
                with path.open("rb") as handle:
                    target.fromfile(handle, path.stat().st_size // target.itemsize)
        return hashes, values


def run(files, bloom_capacity=60_000_000, bloom_fp=0.01, fm_register_bits=12,
        ams_variables=4096, ams_groups=8, ams_seed=4099, hot_threshold=100,
        dgim_window=1_000_000, dgim_queries=(1_000, 10_000, 100_000, 1_000_000),
        work_dir=None, progress=None, skip_exact=False):
    """Stream every file once through all four sketches, then compute exact answers.

    ``files`` is [(hour, path)] in stream order.  The last hour is the Bloom
    probe hour; every earlier hour builds the filter.  With ``skip_exact``
    only the sketches run: no partition files are written and every
    exact-side field is null (the estimates are identical either way).
    """
    say = progress or (lambda message: None)
    files = sorted(files)
    probe_hour = files[-1][0]
    build_hours = [hour for hour, _ in files[:-1]]
    bloom = HashedBloom.for_capacity(bloom_capacity if build_hours else 1, bloom_fp)
    fm = HashedFM(fm_register_bits)
    ams = WeightedAMS(ams_variables, ams_seed, ams_groups)
    # r=2 is the basic book DGIM (same buckets and estimates as fixed Week 7).
    dgim = DGIMReduced(dgim_window, r=2)
    dgim_queries = sorted(k for k in dgim_queries if k <= dgim_window)
    if dgim_window not in dgim_queries:
        dgim_queries.append(dgim_window)

    owned_tmp = None
    if not skip_exact and work_dir is None:
        owned_tmp = tempfile.TemporaryDirectory(prefix="pageviews-exact-")
        work_dir = owned_tmp.name
    if not skip_exact:
        work = Path(work_dir)
        work.mkdir(parents=True, exist_ok=True)
        built, probed = _Partitions(work, "build"), _Partitions(work, "probe")
    keep_exact = not skip_exact

    lines = views = skipped = bloom_hits = 0
    hot_times = deque()  # exact DGIM side: arrival times of one bits inside the window
    checkpoints = []
    per_file = []
    stream_started = time.perf_counter()

    # Locals for the hot loop.
    blake, from_bytes = hashlib.blake2b, int.from_bytes
    data, nbits, khashes = bloom.data, bloom.bits, bloom.hashes
    regs, rbits = fm.registers, fm.register_bits
    rmask, rmax = fm.m - 1, 64 - fm.register_bits + 1
    ams_add = ams.add
    masks = _MASKS

    for hour, path in files:
        is_probe = hour == probe_hour
        if keep_exact:
            parts = probed if is_probe else built
            part_h, part_v = parts.hashes, parts.values
        file_started = time.perf_counter()
        file_views = file_skipped = 0
        t = lines
        with gzip.open(path, "rb") as handle:
            for line in handle:
                pieces = line.rsplit(b" ", 2)
                if len(pieces) != 3 or not pieces[1].isdigit() or b" " not in pieces[0]:
                    file_skipped += 1
                    continue
                c = int(pieces[1])
                h = from_bytes(blake(pieces[0], digest_size=8).digest(), "little")
                t += 1
                file_views += c

                # Flajolet-Martin
                rest = h >> rbits
                rank = (rest & -rest).bit_length() if rest else rmax
                if rank > regs[h & rmask]:
                    regs[h & rmask] = rank

                # Bloom: build hours insert, the probe hour only asks
                p = (h & 0xFFFFFFFF) % nbits
                step = ((h >> 32) | 1) % nbits
                if is_probe:
                    hit = 1
                    for _ in range(khashes):
                        if not data[p >> 3] & masks[p & 7]:
                            hit = 0
                            break
                        p += step
                        if p >= nbits:
                            p -= nbits
                    bloom_hits += hit
                    value = c * 2 + hit
                else:
                    for _ in range(khashes):
                        data[p >> 3] |= masks[p & 7]
                        p += step
                        if p >= nbits:
                            p -= nbits
                    value = c

                # Exact side: remember (hash, value) on disk by partition
                if keep_exact:
                    part = h >> 58
                    part_h[part].append(h)
                    part_v[part].append(value)

                # AMS and DGIM
                ams_add(h, c)
                if c >= hot_threshold:
                    dgim.add_zeros(t - 1 - dgim.time)
                    dgim.add(1)
                    if keep_exact:
                        hot_times.append(t)
                        while hot_times[0] <= t - dgim_window:
                            hot_times.popleft()
        file_lines = t - lines
        lines = t
        views += file_views
        skipped += file_skipped
        if keep_exact:
            parts.flush()
        if not is_probe:
            bloom.inserted += file_lines
        dgim.add_zeros(lines - dgim.time)
        last = max(1, min(dgim_window, lines))
        checkpoints.append({"after_hour": hour, "lines": lines, "last": last,
                            "estimate": dgim.estimate(last) if lines else 0.0,
                            "exact": _exact_recent(hot_times, lines, last) if keep_exact else None})
        seconds = time.perf_counter() - file_started
        per_file.append({"file": path.name, "hour": hour, "lines": file_lines,
                         "views": file_views, "skipped_lines": file_skipped,
                         "seconds": round(seconds, 2)})
        say(f"hour {hour:02d}: {file_lines:,} lines in {seconds:.1f} s")
    stream_seconds = time.perf_counter() - stream_started

    # DGIM answers for several window suffixes at the end of the stream.
    dgim_rows = []
    for k in dgim_queries:
        last = max(1, min(k, lines))
        dgim_rows.append({
            "last_lines": last,
            "estimate": dgim.estimate(last) if lines else 0.0,
            "exact": _exact_recent(hot_times, lines, last) if keep_exact else None,
            "week07_before_fix_estimate":
                week7_original_estimate(dgim.buckets, dgim.time, last) if lines else 0.0,
        })

    exact_started = time.perf_counter()
    exact = _exact_answers(built, probed) if keep_exact else None
    exact_seconds = time.perf_counter() - exact_started
    if owned_tmp is not None:
        owned_tmp.cleanup()

    final = dgim_rows[-1]
    result = {
        "dataset": {
            "files": [path.name for _, path in files],
            "hours": [hour for hour, _ in files],
            "lines": lines, "views": views,
            "bytes_gz": sum(path.stat().st_size for _, path in files),
            "skipped_lines": skipped,
            "key": "wiki_code + ' ' + page_title",
            "per_file": per_file,
        },
        "exact_source": "computed in this run" if keep_exact else "skipped (--skip-exact)",
        "algorithms": {
            "bloom": {
                "question": f"For each page viewed in hour {probe_hour:02d}, was it already "
                            "viewed earlier the same day?",
                "estimate": bloom_hits,
                "build_hours": build_hours, "probe_hour": probe_hour,
                "target_false_positive_rate": bloom_fp,
                "insert_lines": bloom.inserted,
                "sized_for_keys": bloom_capacity if build_hours else 0,
                "bits": bloom.bits, "hashes": bloom.hashes,
                "sketch_memory_bytes": bloom.memory_bytes,
                "exact_memory_note": "a set of one 8-byte hash per key seen before the "
                                     "probe hour",
            },
            "fm": {
                "question": "How many different pages were viewed at least once?",
                "estimate": round(fm.estimate(), 1),
                "registers": fm.m, "combine": "harmonic mean with HyperLogLog bias constant",
                "sketch_memory_bytes": fm.memory_bytes,
                "exact_memory_note": "a set of one 8-byte hash per distinct key",
            },
            "ams": {
                "question": "How concentrated are views on a few pages (second moment F2, "
                            "the surprise number)?",
                "estimate": ams.estimate(), "mean_estimate": ams.mean_estimate(),
                "variables": len(ams.counts), "groups": ams.groups,
                "combine": "median of group means (book Section 4.5.2); mean_estimate is "
                           "the plain average of all variables",
                "stream_arrivals": ams.length,
                "sketch_memory_bytes": ams.memory_bytes,
                "exact_memory_note": "an 8-byte hash and an 8-byte view total per "
                                     "distinct key",
            },
            "dgim": {
                "question": f"Among the last {dgim_window:,} lines, how many are hot pages "
                            f"(at least {hot_threshold} views in that hour)?",
                "estimate": final["estimate"], "exact": final["exact"],
                "window_lines": dgim_window, "hot_threshold_views": hot_threshold,
                "hours_streamed": [hour for hour, _ in files],
                "queries": dgim_rows,
                "checkpoints_end_of_each_hour": checkpoints,
                "buckets": dgim.bucket_count,
                "week07_before_fix_note": "week07_before_fix_* use Week 7's estimate rule "
                                          "before its fix (commit 141deb1), for comparison "
                                          "only",
                "stream_order_note": "lines are in dump order (hour by hour, sorted by wiki "
                                     "and title within an hour), not the order views "
                                     "happened",
                "sketch_memory_bytes": dgim.memory_bytes,
                "exact_memory_bytes": (dgim_window + 7) // 8,
                "exact_memory_note": "one bit per line in the window",
            },
        },
        "runtime_seconds": {"stream_pass_all_sketches": round(stream_seconds, 2),
                            "exact_pass": round(exact_seconds, 2),
                            "total": round(stream_seconds + exact_seconds, 2)},
    }
    if not build_hours:
        result["algorithms"]["bloom"]["note"] = ("only one hour selected: the filter is "
                                                 "empty, every probe is new")
    _set_exact(result, exact)
    finalize(result)
    return result


def _exact_recent(hot_times, now: int, last: int) -> int:
    """Exact one-bits among the latest ``last`` lines, from one-bit arrival times."""
    if not now:
        return 0
    times = list(hot_times)
    return len(times) - bisect_right(times, now - last)


def _exact_answers(built: "_Partitions", probed: "_Partitions") -> dict:
    """Total each partition in turn and return every exact number the report needs."""
    distinct = f2 = distinct_before_probe = 0
    probe_keys = probe_seen = false_pos = false_neg = 0
    for part in range(_Partitions.PARTS):
        hashes, values = built.load(part)
        totals = {}
        get = totals.get
        for h, c in zip(hashes, values):
            totals[h] = get(h, 0) + c
        del hashes, values
        distinct_before_probe += len(totals)
        hashes, values = probed.load(part)
        probe = {}
        for h, value in zip(hashes, values):
            c, hit = value >> 1, value & 1
            before = probe.get(h)
            probe[h] = (c + (before[0] if before else 0), hit)
        del hashes, values
        for h, (c, hit) in probe.items():
            seen = h in totals
            probe_keys += 1
            probe_seen += seen
            false_pos += hit and not seen
            false_neg += seen and not hit
            totals[h] = totals.get(h, 0) + c
        distinct += len(totals)
        f2 += sum(v * v for v in totals.values())
        del totals, probe
    return {"distinct": distinct, "f2": f2, "distinct_before_probe": distinct_before_probe,
            "probe_keys": probe_keys, "probe_seen": probe_seen,
            "false_positives": false_pos, "false_negatives": false_neg}


# Fields that depend on the exact answers.  With --skip-exact they are null,
# and --exact-from copies them from an earlier full run on the same files.
EXACT_FIELDS = {
    "bloom": ("exact", "probe_keys", "truly_new_keys", "false_positives",
              "false_positive_rate", "false_negatives", "keys_inserted",
              "theoretical_false_positive_rate", "exact_memory_bytes"),
    "fm": ("exact", "exact_memory_bytes"),
    "ams": ("exact", "surprise_meaning", "exact_memory_bytes"),
    "dgim": ("exact",),
}


def _set_exact(result: dict, exact) -> None:
    """Write exact-side fields from ``_exact_answers`` output, or nulls when None."""
    algos = result["algorithms"]
    if exact is None:
        for name, fields in EXACT_FIELDS.items():
            for field in fields:
                algos[name][field] = None
        return
    views = result["dataset"]["views"]
    bloom, fm, ams = algos["bloom"], algos["fm"], algos["ams"]
    distinct, f2 = exact["distinct"], exact["f2"]
    truly_new = exact["probe_keys"] - exact["probe_seen"]
    bloom.update({
        "exact": exact["probe_seen"], "probe_keys": exact["probe_keys"],
        "truly_new_keys": truly_new, "false_positives": exact["false_positives"],
        "false_positive_rate": exact["false_positives"] / truly_new if truly_new else 0.0,
        "false_negatives": exact["false_negatives"],
        "keys_inserted": exact["distinct_before_probe"],
        "theoretical_false_positive_rate": HashedBloom(bloom["bits"], bloom["hashes"])
        .theoretical_fp(exact["distinct_before_probe"]),
        "exact_memory_bytes": exact["distinct_before_probe"] * 8,
    })
    fm.update({"exact": distinct, "exact_memory_bytes": distinct * 8})
    ams.update({
        "exact": f2,
        "surprise_meaning": {
            "uniform_f2_if_views_were_spread_evenly": views * views / distinct if distinct else 0,
            "collision_probability_two_random_views_same_page":
                f2 / (views * views) if views else 0,
            "effective_number_of_pages": views * views / f2 if f2 else 0.0,
        },
        "exact_memory_bytes": distinct * 16,
    })


def _err(estimate, exact, digits):
    return None if exact is None else _round(percent_error(estimate, exact), digits)


def finalize(result: dict) -> None:
    """Recompute every error field and plain-English sentence from estimates and exacts."""
    algos = result["algorithms"]
    lines = result["dataset"]["lines"]
    bloom, fm, ams, dgim = algos["bloom"], algos["fm"], algos["ams"], algos["dgim"]
    for name, digits in (("bloom", 4), ("fm", 4), ("ams", 4)):
        algos[name]["error_pct"] = _err(algos[name]["estimate"], algos[name]["exact"], digits)
    ams["mean_error_pct"] = _err(ams["mean_estimate"], ams["exact"], 4)
    for row in dgim["queries"]:
        row["error_pct"] = _err(row["estimate"], row["exact"], 3)
        row["week07_before_fix_error_pct"] = _err(row["week07_before_fix_estimate"],
                                                  row["exact"], 3)
    for row in dgim["checkpoints_end_of_each_hour"]:
        row["error_pct"] = _err(row["estimate"], row["exact"], 3)
    final = dgim["queries"][-1]
    dgim["exact"], dgim["error_pct"] = final["exact"], final["error_pct"]
    errors = [row["error_pct"] for row in dgim["checkpoints_end_of_each_hour"]
              if row["error_pct"] is not None]
    dgim["max_checkpoint_error_pct"] = max(errors) if errors else None

    if not bloom["build_hours"]:
        bloom["tells_us"] = "Only one hour was selected, so nothing was viewed earlier; use 2+ hours."
    elif bloom["exact"] is None or not bloom["probe_keys"]:
        bloom["tells_us"] = (f"The filter says {bloom['estimate']:,} pages read in hour "
                             f"{bloom['probe_hour']:02d} had probably been read earlier that day.")
    else:
        bloom["tells_us"] = (
            f"{bloom['exact'] / bloom['probe_keys']:.0%} of the pages read in hour "
            f"{bloom['probe_hour']:02d} had already been read earlier that day; the filter "
            f"never missed one of those and wrongly said \"seen\" for only "
            f"{bloom['false_positive_rate']:.2%} of the truly new pages.")
    fm["tells_us"] = (f"About {fm['estimate'] / 1e6:.1f} million different pages were viewed "
                      f"in {len(result['dataset']['hours'])} hour(s), from {fm['registers']:,} "
                      "one-byte counters instead of a list of every page.")
    views = result["dataset"]["views"]
    if not views:
        ams["tells_us"] = "No views."
    elif ams["exact"] is None:
        ams["tells_us"] = (f"Two random views land on the same page about "
                           f"{ams['estimate'] / views / views:.3%} of the time, so attention "
                           f"acts like it is spread over only about "
                           f"{views * views / ams['estimate']:,.0f} pages.")
    else:
        ams["tells_us"] = (
            f"Two random views land on the same page {ams['exact'] / views / views:.3%} of "
            f"the time: attention acts like it is spread over only about "
            f"{ams['surprise_meaning']['effective_number_of_pages']:,.0f} pages, not "
            f"{fm['exact']:,}.")
    shown = max(1, min(dgim["window_lines"], lines))
    dgim["tells_us"] = (f"About {dgim['estimate']:,.0f} of the last {shown:,} records "
                        f"({dgim['estimate'] / shown:.2%}) were hot pages with "
                        f"{dgim['hot_threshold_views']}+ views in an hour: almost every page "
                        "gets only a handful of views.")


def fill_exact_from(result: dict, reference: dict) -> dict:
    """Copy exact answers from an earlier full run on the same files, then recompute errors.

    Refuses (ValueError) unless the dataset files, hours, line counts and views
    match.  Also records whether every sketch estimate equals the reference
    run's, which it should, since the seeds are fixed.
    """
    mine, theirs = result["dataset"], reference["dataset"]
    for field in ("files", "hours", "lines", "views", "skipped_lines"):
        if mine.get(field) != theirs.get(field):
            raise ValueError(f"reference run has different dataset {field}; refusing to "
                             "copy its exact answers")
    if reference.get("exact_source") == "skipped (--skip-exact)" or \
            reference["algorithms"]["fm"].get("exact") is None:
        raise ValueError("reference run has no exact answers")
    algos, ref = result["algorithms"], reference["algorithms"]
    for name, fields in EXACT_FIELDS.items():
        for field in fields:
            algos[name][field] = ref[name][field]
    dgim, ref_dgim = algos["dgim"], ref["dgim"]
    for kind in ("queries", "checkpoints_end_of_each_hour"):
        if len(dgim[kind]) != len(ref_dgim[kind]):
            raise ValueError(f"reference run has different DGIM {kind}; refusing")
        for row, ref_row in zip(dgim[kind], ref_dgim[kind]):
            row["exact"] = ref_row["exact"]
    mismatches = [name for name in algos
                  if algos[name]["estimate"] != ref[name]["estimate"]]
    result["exact_source"] = "copied from an earlier full run (--exact-from)"
    result["estimates_match_reference"] = not mismatches
    if mismatches:
        result["estimate_mismatches"] = mismatches
    finalize(result)
    return result
