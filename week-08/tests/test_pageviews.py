"""Week 8 pageview sketches match Week 7 and give hand-checked answers on tiny dumps."""

import gzip
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "week-07" / "scripts"))

from download_pageviews import file_name, file_url, parse_hours  # noqa: E402
from pageviews import (HashedBloom, HashedFM, SkippingDGIM, WeightedAMS,  # noqa: E402
                       find_files, key_hash, parse_line, run)
from streaming import DGIM, AMSSecondMoment, exact_second_moment  # noqa: E402

# A three-hour toy day.  Hour 02 is the Bloom probe hour.
TOY_DAY = {
    0: ["en A 3 0", "en B 1 0", "de A 2 0"],
    1: ["en A 1 0", "fr C 5 0", "this line is broken"],
    2: ["en A 2 0", "fr C 1 0", "en D 4 0", "en E 100 0"],
}
# Worked out by hand:
#   keys: en A, en B, de A, fr C, en D, en E                    -> 6 distinct
#   totals: en A 3+1+2=6, en B 1, de A 2, fr C 5+1=6, en D 4, en E 100
#   F2 = 36 + 1 + 4 + 36 + 16 + 10000 = 10093; views = 119; 9 valid lines
#   probe hour 02: en A and fr C were seen before; en D and en E are new
#   bits for threshold 3, in stream order: 1 0 0 0 1 0 0 1 1


def write_day(folder: Path, day=TOY_DAY):
    """Write a toy day as gzipped hourly dump files and return the folder."""
    for hour, lines in day.items():
        path = folder / f"pageviews-20261027-{hour:02d}0000.gz"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    return folder


class DownloadHelperTests(unittest.TestCase):
    """The downloader builds the right Wikimedia URLs and hour lists."""

    def test_hours_and_urls(self):
        self.assertEqual(parse_hours("00-23"), list(range(24)))
        self.assertEqual(parse_hours("12"), [12])
        self.assertEqual(parse_hours("0,5,7-8"), [0, 5, 7, 8])
        with self.assertRaises(ValueError):
            parse_hours("22-24")
        self.assertEqual(file_name("20261027", 5), "pageviews-20261027-050000.gz")
        self.assertEqual(file_url("20261027", 23),
                         "https://dumps.wikimedia.org/other/pageviews/2026/2026-10/"
                         "pageviews-20261027-230000.gz")


class ParseTests(unittest.TestCase):
    """Dump lines become (wiki + title, views); malformed lines are rejected."""

    def test_parse(self):
        self.assertEqual(parse_line(b"en.m Golden_Horn 9 0\n"), (b"en.m Golden_Horn", 9))
        self.assertEqual(parse_line(b'"" Category:Hungarian 1 0\n'), (b'"" Category:Hungarian', 1))
        self.assertIsNone(parse_line(b"broken\n"))
        self.assertIsNone(parse_line(b"en Title many 0\n"))


class BloomTests(unittest.TestCase):
    """The one-hash Bloom filter has no false negatives and its textbook false-positive rate."""

    def test_sizing_and_positions(self):
        bloom = HashedBloom.for_capacity(1000, 0.01)
        self.assertEqual((bloom.bits, bloom.hashes), (9586, 7))
        h = key_hash(b"en A")
        a, b = h & 0xFFFFFFFF, (h >> 32) | 1
        self.assertEqual(bloom.positions(h), [(a + i * b) % 9586 for i in range(7)])

    def test_no_false_negatives_and_rate_near_theory(self):
        bloom = HashedBloom.for_capacity(2000, 0.01)
        inserted = [key_hash(f"in-{i}".encode()) for i in range(2000)]
        for h in inserted:
            bloom.add_hash(h)
        self.assertTrue(all(bloom.contains_hash(h) for h in inserted))
        probes = [key_hash(f"out-{i}".encode()) for i in range(20000)]
        rate = sum(bloom.contains_hash(h) for h in probes) / len(probes)
        self.assertGreater(rate, 0.003)
        self.assertLess(rate, 0.02)
        self.assertAlmostEqual(bloom.theoretical_fp(2000), 0.01, delta=0.001)


class FMTests(unittest.TestCase):
    """The one-hash FM counter reads the book's trailing-zero R and counts distinct keys closely."""

    def test_register_rank_is_trailing_zeros_plus_one(self):
        fm = HashedFM(4)
        h = (0b1000 << 4) | 0b0011  # register 3, rest has 3 trailing zeros
        self.assertEqual(fm.rank(h), (3, 4))
        fm.add_hash(h)
        self.assertEqual(fm.registers[3], 4)

    def test_estimates_small_and_large_counts(self):
        fm = HashedFM(12)
        for i in range(6):
            fm.add_hash(key_hash(f"k{i}".encode()))
        self.assertAlmostEqual(fm.estimate(), 6, delta=0.5)
        fm = HashedFM(12)
        for i in range(200_000):
            fm.add_hash(key_hash(f"k{i}".encode()))
        self.assertLess(abs(fm.estimate() - 200_000) / 200_000, 0.05)


class WeightedAMSTests(unittest.TestCase):
    """Weighted AMS equals the book's AMS on the expanded stream without expanding it."""

    LINES = [("a", 3), ("b", 1), ("a", 2), ("c", 4), ("b", 2), ("a", 1)]

    def expanded(self):
        return [key for key, count in self.LINES for _ in range(count)]

    def test_book_identity_sum_over_positions_is_f2(self):
        stream = self.expanded()
        total = sum(2 * stream[pos:].count(stream[pos]) - 1 for pos in range(len(stream)))
        self.assertEqual(total, exact_second_moment(stream))  # 6^2 + 3^2 + 4^2 = 61
        self.assertEqual(total, 61)

    def test_matches_brute_force_on_expanded_stream(self):
        ams = WeightedAMS(variables=64, seed=7, groups=8)
        for key, count in self.LINES:
            ams.add(key, count)
        stream = self.expanded()
        for index in range(64):
            # Replay this variable's replacement times on the expanded stream.
            position, draw, chosen = 1, 0, 1
            while position <= len(stream):
                chosen = position
                draw += 1
                position = int(position / ams.uniform(index, draw)) + 1
            key = stream[chosen - 1]
            self.assertEqual(ams.keys[index], key)
            self.assertEqual(ams.counts[index], stream[chosen - 1:].count(key))

    def test_average_is_close_to_exact_like_week_seven(self):
        lines = [(f"k{i % 50}", 1 + i % 7) for i in range(400)]
        stream = [key for key, count in lines for _ in range(count)]
        exact = exact_second_moment(stream)
        ams = WeightedAMS(variables=4096, seed=11, groups=8)
        for key, count in lines:
            ams.add(key, count)
        week07 = AMSSecondMoment(estimators=512, seed=11)
        for key in stream:
            week07.add(key)
        self.assertLess(abs(ams.mean_estimate() - exact) / exact, 0.05)
        self.assertLess(abs(ams.estimate() - exact) / exact, 0.05)
        self.assertLess(abs(week07.estimate() - exact) / exact, 0.15)


class DGIMTests(unittest.TestCase):
    """Skipping zeros keeps Week 7's buckets exactly, and the book estimate matches a hand count."""

    def test_skipping_zeros_keeps_week_seven_buckets(self):
        rng = random.Random(3)
        bits = [1 if rng.random() < 0.2 else 0 for _ in range(3000)]
        slow, fast = DGIM(100), SkippingDGIM(100)
        for t, bit in enumerate(bits, start=1):
            slow.add(bit)
            if bit:
                fast.add_one_at(t)
            if t % 37 == 0:
                fast.advance_to(t)
                self.assertEqual(list(slow.buckets), list(fast.buckets))
        fast.advance_to(len(bits))
        self.assertEqual(list(slow.buckets), list(fast.buckets))
        self.assertEqual(fast.week07_estimate(50), slow.estimate(50))

    def test_book_estimate_by_hand(self):
        dgim = SkippingDGIM(9)
        for t, bit in enumerate([1, 0, 0, 0, 1, 0, 0, 1, 1], start=1):
            if bit:
                dgim.add_one_at(t)
        # Buckets newest first: size 1 @ 9, size 1 @ 8, size 2 @ 5.
        self.assertEqual(list(dgim.buckets), [(1, 9), (1, 8), (2, 5)])
        self.assertEqual(dgim.estimate(9), 1 + 1 + 2 / 2)       # exact 4
        self.assertEqual(dgim.estimate(2), 1 + 1 / 2)           # exact 2
        self.assertEqual(dgim.week07_estimate(9), 4)            # adds the oldest bucket in full


class ToyDayTests(unittest.TestCase):
    """A hand-made three-hour dump gives the exact answers worked out by hand."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = write_day(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_answers_and_estimates(self):
        result = run(find_files(self.folder, set(range(24))), bloom_capacity=1000,
                     hot_threshold=3, dgim_window=9, dgim_queries=(2, 9))
        data, algos = result["dataset"], result["algorithms"]
        self.assertEqual((data["lines"], data["views"], data["skipped_lines"]), (9, 119, 1))
        self.assertEqual(data["hours"], [0, 1, 2])
        self.assertEqual(algos["fm"]["exact"], 6)
        self.assertAlmostEqual(algos["fm"]["estimate"], 6, delta=0.5)
        self.assertEqual(algos["ams"]["exact"], 10093)
        self.assertEqual(algos["bloom"]["exact"], 2)
        self.assertEqual(algos["bloom"]["probe_keys"], 4)
        self.assertEqual(algos["bloom"]["false_negatives"], 0)
        self.assertEqual(algos["bloom"]["keys_inserted"], 4)
        self.assertEqual(algos["dgim"]["exact"], 4)
        self.assertEqual(algos["dgim"]["estimate"], 3.0)
        self.assertEqual(algos["dgim"]["queries"][0]["exact"], 2)
        for name, algo in algos.items():
            for field in ("question", "estimate", "exact", "error_pct", "sketch_memory_bytes",
                          "exact_memory_bytes", "tells_us"):
                self.assertIn(field, algo, f"{name} lacks {field}")

    def test_inline_loops_match_the_sketch_classes(self):
        # A tiny filter forces collisions so the inline probe code is exercised.
        result = run(find_files(self.folder, set(range(24))), bloom_capacity=2,
                     bloom_fp=0.5)
        bloom = HashedBloom.for_capacity(2, 0.5)
        fm = HashedFM(12)
        for hour, lines in TOY_DAY.items():
            for line in lines:
                parsed = parse_line(line.encode())
                if parsed is None:
                    continue
                h = key_hash(parsed[0])
                fm.add_hash(h)
                if hour < 2:
                    bloom.add_hash(h)
        probes = [key_hash(parse_line(line.encode())[0]) for line in TOY_DAY[2]]
        self.assertEqual(result["algorithms"]["bloom"]["estimate"],
                         sum(bloom.contains_hash(h) for h in probes))
        self.assertEqual(result["algorithms"]["fm"]["estimate"], round(fm.estimate(), 1))

    def test_command_line_single_hour(self):
        output = Path(self.tmp.name) / "out.json"
        subprocess.run([sys.executable, str(SCRIPTS / "run_pageviews.py"),
                        "--input-dir", str(self.folder), "--hours", "01",
                        "--output", str(output)], check=True, capture_output=True)
        result = json.loads(output.read_text())
        self.assertEqual(result["dataset"]["hours"], [1])
        self.assertEqual(result["dataset"]["lines"], 2)
        self.assertEqual(set(result["algorithms"]), {"bloom", "fm", "ams", "dgim"})
        self.assertEqual(result["algorithms"]["fm"]["exact"], 2)
        self.assertIn("total", result["runtime_seconds"])


if __name__ == "__main__":
    unittest.main()
