"""DGIM with the textbook's section 4.6.6 "Reducing the Error" rule.

The basic DGIM algorithm (Week 7) keeps one or two buckets of each size
1, 2, 4, ...  Section 4.6.6 generalizes this: keep r-1 or r buckets of each
size (sizes 1 and the largest size present may hold 1..r).  When r+1 buckets
of one size exist, the two oldest merge into one bucket of double size, and
the merge may cascade upward.  The worst-case fractional error of a count
falls from 1/2 (r=2, the basic algorithm) to at most 1/(r-1), at the cost of
keeping more buckets (roughly in proportion to r).

Standard library only (Python 3.9 compatible).
"""

from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional, Tuple, Union


class DGIMReduced:
    """Approximate count of one-bits in the last ``window`` bits, error <= 1/(r-1).

    Buckets are stored per size level: ``self._levels[j]`` holds the
    timestamps (time of the newest one-bit) of every bucket of size 2**j,
    newest on the left.  Every bucket of level j is newer than every bucket
    of level j+1, so a merge moves one bucket from the old end of level j to
    the new end of level j+1: O(1) work per merge, with no list rebuilding.
    Expiry only ever removes the oldest bucket, which sits at the old end of
    the highest level.
    """

    BYTES_PER_BUCKET = 16  # same logical record size as Week 7's DGIM

    def __init__(self, window: int, r: int = 2):
        if window < 1:
            raise ValueError("window must be positive")
        if r < 2:
            raise ValueError("r must be at least 2 (r=2 is the basic algorithm)")
        self.window = window
        self.r = r
        self.time = 0
        self._levels: List[Deque[int]] = []
        self._count = 0  # number of buckets, kept so memory_bytes is O(1)

    def add(self, bit: Union[int, bool]) -> None:
        """Process one bit: maybe start a size-1 bucket, merge, then expire."""
        if bit not in (0, 1, False, True):
            raise ValueError("DGIM accepts only 0 or 1")
        self.time += 1
        if bit:
            levels = self._levels
            if not levels:
                levels.append(deque())
            levels[0].appendleft(self.time)
            self._count += 1
            j = 0
            while len(levels[j]) > self.r:
                # Merge the two oldest buckets of size 2**j.  The merged
                # bucket keeps the newer of the two timestamps.
                levels[j].pop()
                newer = levels[j].pop()
                if j + 1 == len(levels):
                    levels.append(deque())
                levels[j + 1].appendleft(newer)
                self._count -= 1
                j += 1
        self._expire()

    def _expire(self) -> None:
        cutoff = self.time - self.window
        levels = self._levels
        while levels and levels[-1] and levels[-1][-1] <= cutoff:
            levels[-1].pop()
            self._count -= 1
            while levels and not levels[-1]:
                levels.pop()

    def estimate(self, last: Optional[int] = None) -> float:
        """Estimate one-bits in the latest ``last`` bits (default: whole window).

        Following section 4.6.4: add every bucket whose timestamp is inside
        the range, but count the oldest such bucket (the one that may stick
        out past the start of the range) as half its size.
        """
        info = self.estimate_detail(last)
        return info[0]

    def estimate_detail(self, last: Optional[int] = None) -> Tuple[float, int]:
        """Return (estimate, size of the half-counted boundary bucket or 0)."""
        if last is None:
            last = self.window
        if not 1 <= last <= self.window:
            raise ValueError("last must be between 1 and the configured window")
        cutoff = self.time - last
        total = 0
        oldest_size = 0
        size = 1
        for level in self._levels:
            if not level:
                size *= 2
                continue
            if level[-1] > cutoff:
                # Whole level is inside the range.
                total += size * len(level)
                oldest_size = size
                size *= 2
                continue
            # The range starts inside this level: count in-range buckets.
            inside = 0
            for timestamp in level:
                if timestamp > cutoff:
                    inside += 1
                else:
                    break
            total += size * inside
            if inside:
                oldest_size = size
            break
        if not oldest_size:
            return 0.0, 0
        return total - oldest_size / 2, oldest_size

    @property
    def buckets(self) -> List[Tuple[int, int]]:
        """Return (bucket_size, newest_timestamp) pairs, newest bucket first."""
        out = []
        size = 1
        for level in self._levels:
            out.extend((size, timestamp) for timestamp in level)
            size *= 2
        return out

    @property
    def bucket_count(self) -> int:
        """Return the number of buckets currently kept."""
        return self._count

    @property
    def memory_bytes(self) -> int:
        """Return a logical bucket-record footprint, not Python object overhead."""
        return self._count * self.BYTES_PER_BUCKET

    def error_bound(self) -> float:
        """Return the section 4.6.6 worst-case fractional error, 1/(r-1)."""
        return 1.0 / (self.r - 1)
