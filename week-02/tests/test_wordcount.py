"""Exercise the actual mapper/reducer processes with known expected results."""

from pathlib import Path
import subprocess
import sys
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/wordcount"


def run_script(name, text):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name)], input=text,
        text=True, encoding="utf-8", capture_output=True, check=True,
    ).stdout


def wordcount(text):
    mapped = run_script("mapper.py", text)
    # Stand in for Hadoop's grouping/sorting during a local test.
    grouped = "".join(sorted(mapped.splitlines(keepends=True)))
    return run_script("reducer.py", grouped)


class WordCountTests(unittest.TestCase):
    def test_known_counts_across_lines_and_final_group(self):
        self.assertEqual(wordcount("Houston, HOUSTON!\nEagle.\n"),
                         "eagle\t1\nhouston\t2\n")

    def test_token_rules_and_retained_speaker_labels(self):
        text = "00 00 01 02 CC Apollo 11, you're GO. YOU’RE 'go'! air-to-ground A11B"
        self.assertEqual(wordcount(text),
                         "a\t1\nair\t1\napollo\t1\nb\t1\ncc\t1\ngo\t2\n"
                         "ground\t1\nto\t1\nyou're\t2\n")

    def test_empty_and_number_only_input(self):
        for text in ("", "11 00:42 ... --\n"):
            with self.subTest(text=text):
                self.assertEqual(wordcount(text), "")

    def test_reducer_adds_counts_instead_of_counting_lines(self):
        self.assertEqual(run_script("reducer.py", "eagle\t2\neagle\t3\n"), "eagle\t5\n")

    def test_reducer_rejects_invalid_count(self):
        with self.assertRaises(subprocess.CalledProcessError):
            run_script("reducer.py", "eagle\tnot-a-number\n")


if __name__ == "__main__":
    unittest.main()
