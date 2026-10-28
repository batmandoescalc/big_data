"""Streaming sketches stay bounded and give defensible estimates on known streams."""

from pathlib import Path
import sys
import json
import subprocess
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from event_generator import generate_events  # noqa: E402
from streaming import (  # noqa: E402
    AMSSecondMoment, BloomFilter, DGIM, FlajoletMartin, exact_recent_ones,
    exact_second_moment,
)
from benchmark_sizes import run_once, summarize  # noqa: E402


class BloomTests(unittest.TestCase):
    """Bloom filters retain every inserted value while using a fixed bit array."""

    def test_inserted_values_are_never_false_negatives(self):
        filter_ = BloomFilter(bits=256, hashes=4)
        values = ["Eagle", "Tranquility", "Houstøn", "α"]
        for value in values:
            filter_.add(value)
        self.assertTrue(all(value in filter_ for value in values))
        self.assertEqual(filter_.memory_bytes, 32)

    def test_invalid_shape_is_rejected(self):
        with self.assertRaises(ValueError):
            BloomFilter(0, 1)


class FlajoletMartinTests(unittest.TestCase):
    """FM registers merge by maximum and estimate distinct values without a set."""

    def test_merge_matches_single_stream_registers(self):
        values = [f"user-{index % 73}" for index in range(500)]
        whole = FlajoletMartin(32)
        left = FlajoletMartin(32)
        right = FlajoletMartin(32)
        for value in values:
            whole.add(value)
        for value in values[:250]:
            left.add(value)
        for value in values[250:]:
            right.add(value)
        self.assertEqual(whole.registers, left.merge(right).registers)
        self.assertGreater(whole.estimate(), 20)
        self.assertLess(whole.estimate(), 200)

    def test_incompatible_merges_fail(self):
        with self.assertRaises(ValueError):
            FlajoletMartin(4).merge(FlajoletMartin(5))


class AMSTests(unittest.TestCase):
    """AMS distinguishes uniform from concentrated frequency distributions."""

    def test_skew_has_larger_second_moment_and_estimate(self):
        uniform = [f"v-{index % 20}" for index in range(1_000)]
        skewed = ["hot"] * 900 + [f"cold-{index}" for index in range(100)]
        self.assertGreater(exact_second_moment(skewed), exact_second_moment(uniform))
        first, second = AMSSecondMoment(512, 5), AMSSecondMoment(512, 5)
        for value in uniform:
            first.add(value)
        for value in skewed:
            second.add(value)
        self.assertGreater(second.estimate(), first.estimate())

    def test_empty_estimate_is_zero(self):
        self.assertEqual(AMSSecondMoment().estimate(), 0.0)


class DGIMTests(unittest.TestCase):
    """DGIM keeps a logarithmic bucket summary of recent binary events."""

    def test_count_is_reasonable_and_bounded(self):
        bits = [index % 3 == 0 for index in range(1, 301)]
        sketch = DGIM(128)
        for bit in bits:
            sketch.add(bit)
        exact = exact_recent_ones(bits, 128)
        self.assertLessEqual(abs(sketch.estimate() - exact), exact / 2 + 2)
        self.assertLess(sketch.memory_bytes, 16 * 30)

    def test_nonbinary_input_fails(self):
        with self.assertRaises(ValueError):
            DGIM(10).add(2)


class GeneratorTests(unittest.TestCase):
    """Generated streams are repeatable and produced one event at a time."""

    def test_fixed_seed_repeats_and_sequence_is_contiguous(self):
        first = list(generate_events(3, 5, 5, 0.1, 8))
        second = list(generate_events(3, 5, 5, 0.1, 8))
        self.assertEqual(first, second)
        self.assertEqual([event["sequence"] for event in first], [1, 2, 3])


class HadoopFMTests(unittest.TestCase):
    """The map-side FM summaries merge exactly as the single-process registers do."""

    HADOOP = SCRIPTS / "hadoop"

    def test_mapper_reducer_matches_single_process_registers(self):
        events = list(generate_events(12, 7, 3, 0.0, 22))
        payload = "".join(json.dumps(event) + "\n" for event in events)
        mapper = subprocess.run([sys.executable, str(self.HADOOP / "fm_mapper.py"), "16"],
                                input=payload, text=True, encoding="utf-8",
                                capture_output=True, check=True)
        reducer = subprocess.run([sys.executable, str(self.HADOOP / "fm_reducer.py")],
                                 input="".join(sorted(mapper.stdout.splitlines(True))), text=True,
                                 encoding="utf-8", capture_output=True, check=True)
        whole = FlajoletMartin(16)
        for event in events:
            whole.add(event["user_id"])
        reduced = {int(line.split("\t")[0]): int(line.split("\t")[1])
                   for line in reducer.stdout.splitlines()}
        self.assertEqual(reduced, dict(enumerate(whole.registers)))

    def test_hadoop_launcher_refuses_existing_output(self):
        launcher = (self.HADOOP / "run-fm-hadoop.sh").read_text(encoding="utf-8")
        self.assertIn("Refusing to overwrite existing HDFS output", launcher)


class RepeatedBenchmarkTests(unittest.TestCase):
    """Repeated stream summaries retain fixed sketches while exact state grows."""

    def test_summary_has_one_row_per_size_and_fixed_fm_memory(self):
        summary = summarize([run_once(100, 1, users=50), run_once(200, 2, users=50)])
        self.assertEqual([row["events"] for row in summary], [100, 200])
        self.assertEqual([row["fm_bytes"] for row in summary], [128, 128])


if __name__ == "__main__":
    unittest.main()
