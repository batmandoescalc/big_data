"""Shingling, minhash, LSH banding, and the Hadoop reducers on known inputs."""

from pathlib import Path
import os
import random
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
HADOOP = SCRIPTS / "hadoop"
WEEK2_MAPPER = Path(__file__).resolve().parents[2] / "week-02/scripts/wordcount/mapper.py"
sys.path.insert(0, str(SCRIPTS))

import lsh  # noqa: E402
import minhash  # noqa: E402
import shingle  # noqa: E402


def run(script, text, *args):
    """Run a Hadoop script as Streaming would, with lsh.py importable."""
    return subprocess.run(
        [sys.executable, str(script), *args], input=text, text=True, encoding="utf-8",
        capture_output=True, check=True, env={"PYTHONPATH": str(SCRIPTS)},
    ).stdout


class ShingleTests(unittest.TestCase):
    def test_empty_input_has_no_shingles(self):
        self.assertEqual(shingle.words(""), [])
        self.assertEqual(shingle.word_shingles([], 3), set())
        self.assertEqual(shingle.char_shingles("", 5), set())
        self.assertEqual(shingle.window_starts(0, 50, 25), [])

    def test_fewer_than_k_words_has_no_shingles(self):
        self.assertEqual(shingle.word_shingles(["roger", "houston"], 3), set())
        self.assertEqual(shingle.char_shingles("go", 5), set())

    def test_exactly_k_words_is_one_shingle(self):
        self.assertEqual(shingle.word_shingles(["the", "eagle", "has"], 3), {"the eagle has"})

    def test_word_rules_match_week_two_mapper(self):
        text = "00 00 01 02 CC Apollo 11, you're GO. YOU’RE 'go'! air-to-ground A11B\n"
        mapped = subprocess.run([sys.executable, str(WEEK2_MAPPER)], input=text, text=True,
                                encoding="utf-8", capture_output=True, check=True).stdout
        self.assertEqual(shingle.words(text), [line.split("\t")[0] for line in mapped.splitlines()])

    def test_char_shingles_ignore_case_punctuation_and_numbers(self):
        self.assertEqual(shingle.char_shingles("Eagle, 11 HAS!", 4),
                         shingle.char_shingles("eagle has", 4))

    def test_stable_hash_is_fixed_crc32_value(self):
        # A fixed value proves the hash does not change between processes or machines.
        self.assertEqual(shingle.stable_hash("the eagle has"), 216341939)
        out = subprocess.run(
            [sys.executable, "-c", "import shingle; print(shingle.stable_hash('the eagle has'))"],
            text=True, capture_output=True, check=True, env={"PYTHONPATH": str(SCRIPTS)}).stdout
        self.assertEqual(int(out), 216341939)

    def test_windows_cover_every_word_including_the_tail(self):
        self.assertEqual(shingle.window_starts(120, 50, 25), [0, 25, 50, 70])
        self.assertEqual(shingle.window_starts(30, 50, 25), [0])
        self.assertEqual(shingle.window_starts(100, 50, 25), [0, 25, 50])


class MinhashTests(unittest.TestCase):
    params = minhash.hash_params(200, seed=7)

    def test_identical_sets_give_identical_signatures(self):
        a = shingle.hashed({"the eagle has", "eagle has landed"})
        b = shingle.hashed({"eagle has landed", "the eagle has"})
        self.assertEqual(minhash.signature(a, self.params), minhash.signature(b, self.params))
        self.assertEqual(minhash.estimate(minhash.signature(a, self.params),
                                          minhash.signature(b, self.params)), 1.0)

    def test_empty_set_is_rejected(self):
        with self.assertRaises(ValueError):
            minhash.signature(set(), self.params)

    def test_exact_jaccard(self):
        self.assertEqual(minhash.jaccard({1, 2, 3}, {2, 3, 4}), 0.5)
        self.assertEqual(minhash.jaccard({1}, {2}), 0.0)
        self.assertEqual(minhash.jaccard(set(), set()), 0.0)

    def test_estimate_is_close_to_known_jaccard(self):
        # Sets of 400 elements sharing `shared` of them have Jaccard shared/(800-shared).
        rng = random.Random(11)
        for target in (0.2, 0.5, 0.8):
            shared = round(800 * target / (1 + target))
            pool = rng.sample(range(1 << 32), 800 - shared)
            a = set(pool[:400])
            b = set(pool[:shared]) | set(pool[400:800 - shared])
            exact = minhash.jaccard(a, b)
            estimate = minhash.estimate(minhash.signature(a, self.params),
                                        minhash.signature(b, self.params))
            # Standard deviation is sqrt(J(1-J)/n) <= 0.036 for n = 200; allow 3 of them.
            with self.subTest(target=target):
                self.assertAlmostEqual(exact, target, delta=0.01)
                self.assertLess(abs(estimate - exact), 3 * 0.5 / 200 ** 0.5)

    def test_seed_makes_parameters_repeatable(self):
        self.assertEqual(minhash.hash_params(5, 1), minhash.hash_params(5, 1))
        self.assertNotEqual(minhash.hash_params(5, 1), minhash.hash_params(5, 2))


class BandingTests(unittest.TestCase):
    # Hand-built 4-row signatures, b = 2 bands of r = 2 rows.
    toy = {
        "A": [1, 2, 3, 4],
        "B": [1, 2, 9, 9],   # shares band 0 with A
        "C": [7, 8, 3, 4],   # shares band 1 with A
        "D": [5, 6, 7, 8],   # shares nothing with anyone
    }

    def test_toy_example_candidates(self):
        self.assertEqual(lsh.candidates(self.toy, 2, 2), {("A", "B"), ("A", "C")})

    def test_threshold_and_probability(self):
        self.assertAlmostEqual(lsh.threshold(20, 5), 0.5493, places=4)
        self.assertEqual(lsh.probability(0.0, 20, 5), 0.0)
        self.assertEqual(lsh.probability(1.0, 20, 5), 1.0)
        self.assertAlmostEqual(lsh.probability(0.8, 20, 5), 0.99964, places=5)

    def test_wrong_signature_length_is_rejected(self):
        with self.assertRaises(ValueError):
            list(lsh.band_keys([1, 2, 3], 2, 2))

    def test_same_band_values_in_different_bands_do_not_collide(self):
        self.assertEqual(lsh.candidates({"X": [1, 1, 2, 2], "Y": [2, 2, 1, 1]}, 2, 2), set())


class HadoopTests(unittest.TestCase):
    signatures = "".join(f"{k}\t{' '.join(map(str, v))}\n" for k, v in BandingTests.toy.items())

    def pipeline(self, shuffle_seed):
        mapped = run(HADOOP / "lsh_mapper.py", self.signatures, "2", "2").splitlines(keepends=True)
        # Group by key like Hadoop, but deliberately scramble value order within each key.
        random.Random(shuffle_seed).shuffle(mapped)
        grouped = sorted(mapped, key=lambda line: line.split("\t")[0])
        pairs = run(HADOOP / "lsh_reducer.py", "".join(grouped))
        return run(HADOOP / "dedupe_reducer.py", "".join(sorted(pairs.splitlines(keepends=True))))

    def test_hadoop_matches_local_banding_for_any_value_order(self):
        for seed in range(6):
            with self.subTest(seed=seed):
                self.assertEqual(self.pipeline(seed), "A\tB\t1\nA\tC\t1\n")

    def test_reducer_orders_pairs_when_values_arrive_reversed(self):
        out = run(HADOOP / "lsh_reducer.py", "0:x\tC\n0:x\tA\n0:x\tB\n1:y\tD\n")
        self.assertEqual(out, "A\tB\nA\tC\nB\tC\n")

    def test_dedupe_counts_bands_that_agreed(self):
        out = run(HADOOP / "dedupe_reducer.py", "A\tB\nA\tB\nA\tC\n")
        self.assertEqual(out, "A\tB\t2\nA\tC\t1\n")

    def test_dedupe_ignores_empty_value_from_two_field_key(self):
        # Hadoop delivers 'key<TAB>value'; here the key is both IDs and the value is empty.
        out = run(HADOOP / "dedupe_reducer.py", "A\tB\t\nA\tB\t\n")
        self.assertEqual(out, "A\tB\t2\n")

    def test_mapper_imports_lsh_from_streaming_symlink_layout(self):
        # Hadoop Streaming symlinks each -files entry into the task directory from
        # its own cache directory. The first cluster run failed on this layout.
        launcher = (HADOOP / "run-hadoop.sh").read_text()
        self.assertIn("-cmdenv PYTHONPATH=.", launcher)
        with tempfile.TemporaryDirectory() as tmp:
            task = Path(tmp, "task")
            task.mkdir()
            for source in (SCRIPTS / "lsh.py", HADOOP / "lsh_mapper.py"):
                cache = Path(tmp, "cache-" + source.stem)
                cache.mkdir()
                (cache / source.name).write_bytes(source.read_bytes())
                os.symlink(cache / source.name, task / source.name)
            result = subprocess.run(
                [sys.executable, "lsh_mapper.py", "2", "2"], input="x\t1 2 3 4\n", text=True,
                capture_output=True, cwd=task, env={"PYTHONPATH": "."})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(result.stdout.splitlines()), 2)

    def test_empty_input(self):
        self.assertEqual(run(HADOOP / "lsh_reducer.py", ""), "")
        self.assertEqual(run(HADOOP / "dedupe_reducer.py", ""), "")


if __name__ == "__main__":
    unittest.main()
