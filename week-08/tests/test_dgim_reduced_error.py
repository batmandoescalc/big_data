"""Section 4.6.6 DGIM keeps r-1..r buckets per size and stays within 1/(r-1)."""

import gzip
import importlib.util
from pathlib import Path
import random
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "week-08" / "scripts"))

from dgim_reduced_error import DGIMReduced  # noqa: E402
import dgim_study  # noqa: E402


def _load_week07():
    """Import Week 7's streaming.py under its own name, so no module collides."""
    spec = importlib.util.spec_from_file_location(
        "week07_streaming", ROOT / "week-07" / "scripts" / "streaming.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WEEK07 = _load_week07()


def feed(sketch, bits):
    for bit in bits:
        sketch.add(bit)
    return sketch


class HandCheckedTests(unittest.TestCase):
    """Tiny streams give the bucket lists and estimates worked out by hand."""

    def test_basic_r2_merges_like_the_textbook(self):
        # Ones at t=1..7: sizes 1,2,4 after the ripple of merges.
        sketch = feed(DGIMReduced(100, 2), [1] * 7)
        self.assertEqual(sketch.buckets, [(1, 7), (2, 6), (4, 4)])
        # Oldest bucket (size 4) is counted as half: 1 + 2 + 2.
        self.assertEqual(sketch.estimate(), 5.0)

    def test_r3_allows_three_buckets_before_merging(self):
        sketch = feed(DGIMReduced(100, 3), [1, 1, 1])
        self.assertEqual(sketch.buckets, [(1, 3), (1, 2), (1, 1)])
        sketch.add(1)  # a 4th size-1 bucket: the two oldest merge
        self.assertEqual(sketch.buckets, [(1, 4), (1, 3), (2, 2)])
        self.assertEqual(sketch.estimate(4), 3.0)  # exact 4
        self.assertEqual(sketch.estimate(3), 3.0)  # exact 3

    def test_zeros_change_nothing_but_time(self):
        sketch = feed(DGIMReduced(10, 3), [1, 0, 0, 1])
        self.assertEqual(sketch.buckets, [(1, 4), (1, 1)])
        self.assertEqual(sketch.estimate(2), 0.5)  # exact 1: size-1 half rule

    def test_buckets_expire_after_the_window(self):
        sketch = feed(DGIMReduced(4, 2), [1, 1, 0, 0, 0])
        self.assertEqual(sketch.buckets, [(1, 2)])
        sketch.add(0)
        self.assertEqual(sketch.buckets, [])
        self.assertEqual(sketch.estimate(), 0.0)
        self.assertEqual(sketch.memory_bytes, 0)

    def test_invalid_input_is_rejected(self):
        with self.assertRaises(ValueError):
            DGIMReduced(0)
        with self.assertRaises(ValueError):
            DGIMReduced(10, r=1)
        with self.assertRaises(ValueError):
            DGIMReduced(10).add(2)
        with self.assertRaises(ValueError):
            DGIMReduced(10).estimate(11)


class Week07EquivalenceTests(unittest.TestCase):
    """With r=2 the buckets and estimates are exactly Week 7's DGIM."""

    def test_r2_keeps_identical_buckets_and_estimates_to_week07(self):
        rng = random.Random(7)
        for p in (0.1, 0.5, 0.9):
            old, new = WEEK07.DGIM(64), DGIMReduced(64, 2)
            for _ in range(2_000):
                bit = rng.random() < p
                old.add(bit)
                new.add(bit)
                self.assertEqual(list(old.buckets), new.buckets)
                self.assertEqual(old.memory_bytes, new.memory_bytes)
                for k in (1, 2, 7, 30, 63, 64):
                    self.assertEqual(old.estimate(k), new.estimate(k))

    def test_eight_ones_window_five_matches_the_book(self):
        # Ones at t=1..8 with window 5: exact count is 5 (t=4..8).  The book
        # rule halves the size-4 bucket that sticks out: 1 + 1 + 2 + 2 = 6.
        old = feed(WEEK07.DGIM(5), [1] * 8)
        new = feed(DGIMReduced(5, 2), [1] * 8)
        self.assertEqual(new.estimate(), 6.0)
        self.assertEqual(old.estimate(), 6.0)


class Week7BeforeFixTests(unittest.TestCase):
    """The frozen pre-fix Week 7 rule (commit 141deb1) gives its old answers."""

    def test_old_rule_overcounted_eight_ones_window_five(self):
        sketch = feed(DGIMReduced(5, 2), [1] * 8)
        # Old rule: every in-range bucket in full, 1 + 1 + 2 + 4 = 8.
        self.assertEqual(
            dgim_study.week7_original_estimate(sketch.buckets, sketch.time, 5), 8.0)

    def test_old_rule_added_half_of_an_expired_bucket(self):
        # Ones at t=1 and t=2, then zeros; query the last 7 bits at t=8.
        sketch = feed(DGIMReduced(8, 2), [1, 1, 0, 0, 0, 0, 0, 0])
        self.assertEqual(sketch.buckets, [(1, 2), (1, 1)])
        self.assertEqual(
            dgim_study.week7_original_estimate(sketch.buckets, sketch.time, 7), 1.5)
        self.assertEqual(sketch.estimate(7), 0.5)  # exact 1


class ErrorBoundTests(unittest.TestCase):
    """Brute force: every query error stays within the book's 1/(r-1) bound."""

    def test_bound_holds_on_random_streams(self):
        window = 96
        for r in (2, 3, 4, 6):
            for seed, p in ((1, 0.2), (2, 0.6), (3, 0.95)):
                rng = random.Random(seed)
                sketch, bits = DGIMReduced(window, r), []
                worst = 0.0
                for _ in range(1_500):
                    bit = 1 if rng.random() < p else 0
                    bits.append(bit)
                    sketch.add(bit)
                    for k in range(1, min(window, len(bits)) + 1):
                        exact = sum(bits[-k:])
                        estimate, boundary = sketch.estimate_detail(k)
                        if boundary >= 2:  # the book's analysis assumes j >= 1
                            worst = max(worst, abs(estimate - exact) / exact)
                self.assertLessEqual(worst, 1 / (r - 1), (r, seed))

    def test_size1_boundary_only_happens_on_tiny_counts(self):
        # The book's formula needs the half-counted bucket to have size >= 2.
        # A size-1 one can only be oldest when the range holds <= r ones.
        rng = random.Random(4)
        for r in (2, 5):
            sketch, bits = DGIMReduced(50, r), []
            for _ in range(800):
                bit = 1 if rng.random() < 0.3 else 0
                bits.append(bit)
                sketch.add(bit)
                for k in range(1, min(50, len(bits)) + 1):
                    _, boundary = sketch.estimate_detail(k)
                    if boundary == 1:
                        self.assertLessEqual(sum(bits[-k:]), r)

    def test_bucket_counts_per_size_follow_the_rule(self):
        rng = random.Random(5)
        for r in (2, 3, 5):
            sketch = DGIMReduced(200, r)
            for _ in range(3_000):
                sketch.add(rng.random() < 0.5)
                sizes = [len(level) for level in sketch._levels]
                self.assertTrue(all(count <= r for count in sizes))
                # Every size below the largest keeps at least r-1 buckets.
                self.assertTrue(all(count >= r - 1 for count in sizes[:-1]))
                self.assertEqual(sketch.bucket_count, len(sketch.buckets))


class StudyTests(unittest.TestCase):
    """The study script reads pageviews lines, scores queries and draws the chart."""

    def test_hot_lines_become_ones(self):
        lines = ["en Main_Page 5000 0", "en Rare_page 3 0", "de Seite 100 0",
                 "broken line", "fr Page 99 0"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pageviews.gz"
            with gzip.open(path, "wt", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
            self.assertEqual(list(dgim_study.wikipedia_bits(path, 100)), [1, 0, 1, 0, 0])
            self.assertEqual(list(dgim_study.wikipedia_bits(path, 100, max_lines=2)), [1, 0])

    def test_small_synthetic_study_holds_the_bound_and_charts(self):
        window, rs = 2_000, [2, 3, 5]
        ks = dgim_study.query_lengths(window, 20, 1)
        self.assertEqual((ks[0], ks[-1]), (1, window))
        times = dgim_study.spaced_times(window, 8_000, 10, 1)
        result = dgim_study.run_stream(
            "synthetic", dgim_study.synthetic_bits(8_000, 0.05, 1),
            window, rs, times, ks, 1)
        self.assertEqual(result["bits"], 8_000)
        rows = result["by_r"]
        self.assertTrue(all(row["bound_held"] for row in rows))
        self.assertGreater(rows[0]["mean_error"], rows[-1]["mean_error"])
        self.assertLess(rows[0]["max_memory_bytes"], rows[-1]["max_memory_bytes"])
        svg = dgim_study.svg_chart({"window": window, "streams": [result]})
        self.assertIn("shrinks DGIM", svg)
        self.assertIn("prefers-color-scheme: dark", svg)
        self.assertNotIn("\u2014", svg)


if __name__ == "__main__":
    unittest.main()
