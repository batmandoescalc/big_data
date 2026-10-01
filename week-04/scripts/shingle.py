#!/usr/bin/env python3
"""Turn text into k-shingles and hash each shingle to a stable 32-bit integer.

Word rules match week-02/scripts/wordcount/mapper.py: lowercase English letters,
internal apostrophes kept, curly apostrophes normalized, everything else is a
separator. Hashes use crc32, never Python's hash(), which is salted per process
and would give different values in different Hadoop tasks.
"""

import re
import zlib


# Same pattern as the Week 2 word-count mapper.
WORD = re.compile(r"[a-z]+(?:'[a-z]+)*")


def words(text):
    """Return the lowercase words of text using the Week 2 rules."""
    return WORD.findall(text.lower().replace("’", "'"))


def stable_hash(shingle):
    """Hash a shingle string to an unsigned 32-bit integer, identical on every machine."""
    return zlib.crc32(shingle.encode("utf-8"))


def word_shingles(tokens, k):
    """Return the set of k consecutive words, joined by spaces.

    Fewer than k words yields an empty set; a window that short has no k-shingle.
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    return {" ".join(tokens[i:i + k]) for i in range(len(tokens) - k + 1)}


def char_shingles(text, k):
    """Return the set of k consecutive characters after normalizing to words.

    Joining the words with single spaces removes punctuation, numbers, and
    layout differences, so two copies of a passage shingle the same way.
    """
    if k < 1:
        raise ValueError("k must be at least 1")
    normalized = " ".join(words(text))
    return {normalized[i:i + k] for i in range(len(normalized) - k + 1)}


def hashed(shingles):
    """Map a set of shingle strings to a set of 32-bit integers."""
    return {stable_hash(s) for s in shingles}


def window_starts(n_words, size, stride):
    """Start offsets of fixed word windows that together cover every word.

    Windows begin every `stride` words. A final window ending on the last word
    is added when the regular steps would leave a tail uncovered.
    """
    if size < 1 or stride < 1:
        raise ValueError("size and stride must be positive")
    if n_words == 0:
        return []
    last = max(n_words - size, 0)
    starts = list(range(0, last + 1, stride))
    if starts[-1] != last:
        starts.append(last)
    return starts
