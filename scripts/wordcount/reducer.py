#!/usr/bin/env python3
"""Sum tab-separated counts; input must be sorted by word."""

import sys


def main():
    current_word = None
    total = 0

    for line in sys.stdin:
        word, count = line.rstrip("\n").split("\t")
        if current_word is not None and word != current_word:
            print(f"{current_word}\t{total}")
            total = 0
        current_word = word
        total += int(count)

    # The last word has no following word to trigger printing inside the loop.
    if current_word is not None:
        print(f"{current_word}\t{total}")


if __name__ == "__main__":
    main()
