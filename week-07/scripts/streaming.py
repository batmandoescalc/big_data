"""Small, deterministic streaming sketches used in the Week 7 study.

The implementations deliberately use only the Python standard library.  They
process one record at a time and retain summaries rather than the whole stream.
They are teaching implementations, not production replacements for mature
stream-processing libraries.
"""

from __future__ import annotations

import hashlib
import math
import random
from collections import Counter, deque
from typing import Optional, Union


def stable_hash(value: object, seed: int = 0) -> int:
    """Return a repeatable 64-bit hash, independent of Python hash randomization."""
    payload = f"{seed}|{value}".encode("utf-8")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")


class BloomFilter:
    """Probabilistic membership filter: no false negatives, possible positives."""

    def __init__(self, bits: int = 8192, hashes: int = 5):
        if bits < 1 or hashes < 1:
            raise ValueError("bits and hashes must both be positive")
        self.bits = bits
        self.hashes = hashes
        self._data = bytearray((bits + 7) // 8)

    def _positions(self, value: object):
        for index in range(self.hashes):
            yield stable_hash(value, index) % self.bits

    def add(self, value: object) -> None:
        """Record one value."""
        for position in self._positions(value):
            self._data[position // 8] |= 1 << (position % 8)

    def __contains__(self, value: object) -> bool:
        return all(self._data[position // 8] & (1 << (position % 8))
                   for position in self._positions(value))

    @property
    def memory_bytes(self) -> int:
        """Return bytes retained by the bit array, excluding interpreter overhead."""
        return len(self._data)


class FlajoletMartin:
    """Multi-register distinct-count sketch using trailing-zero hash observations."""

    # E[2**R] correction for the classic one-register FM statistic.
    PHI = 0.77351

    def __init__(self, registers: int = 64):
        if registers < 1:
            raise ValueError("registers must be positive")
        self.registers = [0] * registers

    @staticmethod
    def trailing_zeros(number: int) -> int:
        """Count zero bits at the right of a nonzero integer."""
        if number == 0:
            return 64
        return (number & -number).bit_length() - 1

    def add(self, value: object) -> None:
        """Update every independent register with one stream value."""
        for seed, current in enumerate(self.registers):
            observed = self.trailing_zeros(stable_hash(value, seed))
            if observed > current:
                self.registers[seed] = observed

    def estimate(self) -> float:
        """Return a harmonic aggregate of independently corrected FM estimates.

        A simple arithmetic mean lets a rare long run of zero hash bits
        dominate the answer.  The harmonic aggregate retains the classic FM
        register observation but is much less sensitive to that heavy tail.
        """
        estimates = [2.0 ** register / self.PHI for register in self.registers]
        return len(estimates) / sum(1.0 / estimate for estimate in estimates)

    def merge(self, other: "FlajoletMartin") -> "FlajoletMartin":
        """Merge a compatible mapper summary by retaining each register maximum."""
        if len(self.registers) != len(other.registers):
            raise ValueError("register counts must match")
        merged = FlajoletMartin(len(self.registers))
        merged.registers = [max(left, right)
                            for left, right in zip(self.registers, other.registers)]
        return merged

    @property
    def memory_bytes(self) -> int:
        """Return the compact logical size of the register array."""
        return len(self.registers)


class AMSSecondMoment:
    """Reservoir-selected AMS estimators for the second frequency moment F2."""

    def __init__(self, estimators: int = 64, seed: int = 4099):
        if estimators < 1:
            raise ValueError("estimators must be positive")
        self._rng = random.Random(seed)
        self.samples = [None] * estimators
        self.counts = [0] * estimators
        self.length = 0

    def add(self, value: object) -> None:
        """Update each reservoir sample and its suffix frequency counter."""
        self.length += 1
        for index in range(len(self.samples)):
            if self._rng.randrange(self.length) == 0:
                self.samples[index] = value
                self.counts[index] = 1
            elif self.samples[index] == value:
                self.counts[index] += 1

    def estimate(self) -> float:
        """Return the mean unbiased AMS estimate for F2."""
        if not self.length:
            return 0.0
        return sum(self.length * (2 * count - 1) for count in self.counts) / len(self.counts)

    @property
    def memory_bytes(self) -> int:
        """Return a conservative logical counter footprint, excluding stored keys."""
        return len(self.samples) * 16


class DGIM:
    """Approximate count of one-bits in the most recent bounded event window."""

    def __init__(self, window: int):
        if window < 1:
            raise ValueError("window must be positive")
        self.window = window
        self.time = 0
        # Each item is (bucket_size, timestamp_of_newest_bit), newest first.
        self.buckets: deque[tuple[int, int]] = deque()

    def add(self, bit: Union[int, bool]) -> None:
        """Process one binary event and compact old buckets as DGIM requires."""
        if bit not in (0, 1, False, True):
            raise ValueError("DGIM accepts only 0 or 1")
        self.time += 1
        if bit:
            self.buckets.appendleft((1, self.time))
            self._compact()
        self._expire()

    def _compact(self) -> None:
        # At most two buckets of a size may remain.  Merge the two oldest
        # matching buckets, assigning the newer one's timestamp to the merge.
        changed = True
        while changed:
            changed = False
            sizes = sorted({size for size, _ in self.buckets})
            for size in sizes:
                positions = [index for index, item in enumerate(self.buckets)
                             if item[0] == size]
                if len(positions) > 2:
                    older, newer = positions[-1], positions[-2]
                    items = list(self.buckets)
                    timestamp = items[newer][1]
                    del items[older]
                    del items[newer]
                    items.insert(newer, (size * 2, timestamp))
                    self.buckets = deque(items)
                    changed = True
                    break

    def _expire(self) -> None:
        cutoff = self.time - self.window
        while self.buckets and self.buckets[-1][1] <= cutoff:
            self.buckets.pop()

    def estimate(self, last: Optional[int] = None) -> float:
        """Estimate one-bits in the latest ``last`` events (default full window)."""
        if last is None:
            last = self.window
        if not 1 <= last <= self.window:
            raise ValueError("last must be between 1 and the configured window")
        cutoff = self.time - last
        total = 0.0
        for size, timestamp in self.buckets:
            if timestamp > cutoff:
                total += size
            else:
                total += size / 2
                break
        return total

    @property
    def memory_bytes(self) -> int:
        """Return a logical bucket-record footprint, not Python object overhead."""
        return len(self.buckets) * 16


def exact_second_moment(values) -> int:
    """Return F2 exactly for a finite reference stream."""
    return sum(count * count for count in Counter(values).values())


def exact_recent_ones(bits, last: int) -> int:
    """Return the exact number of ones in a finite stream suffix."""
    return sum(bits[-last:])
