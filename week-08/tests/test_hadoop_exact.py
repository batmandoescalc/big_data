"""The Hadoop exact distinct-count job gives the same answer as one process."""

from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
HADOOP = SCRIPTS / "hadoop"
WEEK7 = SCRIPTS.parents[1] / "week-07" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from pageviews import key_hash, parse_line  # noqa: E402

MAPPER = HADOOP / "exact_distinct_mapper.py"
REDUCER = HADOOP / "exact_distinct_reducer.py"
FINISH = HADOOP / "exact_distinct_finish.py"

# Three mapper inputs.  Pages repeat inside one input and across inputs.
PARTS = [
    b"en Main_Page 500 0\nen Cat 3 0\nde Hund 7 0\nbad line\nfr Chat 2 0\n",
    b"en Main_Page 410 0\nen Dog 1 0\nes Perro 4 0\nen Cat 9 0\n",
    b"en Cat 1 0\nen Cat 2 0\nit Gatto 6 0\nen Main_Page 1 0\n",
]


def run_script(path, data, *args):
    return subprocess.run([sys.executable, str(path), *args], input=data,
                          stdout=subprocess.PIPE, check=True).stdout


def single_process_distinct(parts):
    """The plain answer: a set of every valid line's key hash."""
    seen = set()
    for part in parts:
        for line in part.splitlines():
            parsed = parse_line(line)
            if parsed:
                seen.add(key_hash(parsed[0]))
    return len(seen)


def hadoop_distinct(parts, reducers=1):
    """Mapper per input, sort, split by key across reducers, reduce, finish."""
    mapped = b"".join(run_script(MAPPER, part) for part in parts)
    lines = mapped.splitlines(keepends=True)
    part_files = b""
    for number in range(reducers):
        # Hadoop sends every copy of a key to the same reducer, sorted.  It
        # also hands the reducer "key<TAB>value" even when the value is empty.
        mine = sorted(line for line in lines
                      if int(line.split(b"\t")[0], 16) % reducers == number)
        shuffled = b"".join(line.rstrip(b"\n") + b"\t\n" for line in mine)
        part_files += run_script(REDUCER, shuffled)
    return int(run_script(FINISH, part_files).decode())


class HadoopExactDistinctTests(unittest.TestCase):
    """Mapper, shuffle sort, reducer and finish step match a plain set of keys."""

    def test_mapper_emits_one_fixed_width_hash_per_valid_line(self):
        out = run_script(MAPPER, PARTS[0]).decode().splitlines()
        self.assertEqual(len(out), 4)  # 5 lines, 1 malformed
        self.assertEqual(out[0], f"{key_hash(b'en Main_Page'):016x}")
        self.assertTrue(all(len(line) == 16 for line in out))
        self.assertEqual(run_script(MAPPER, b"not a pageview line\n"), b"")

    def test_one_mapper_one_reducer_matches_single_process(self):
        self.assertEqual(hadoop_distinct([b"".join(PARTS)]), single_process_distinct(PARTS))
        self.assertEqual(single_process_distinct(PARTS), 7)  # counted by hand

    def test_several_mapper_inputs_match_single_process(self):
        self.assertEqual(hadoop_distinct(PARTS), 7)

    def test_two_reducers_split_by_key_add_up_to_the_same_count(self):
        self.assertEqual(hadoop_distinct(PARTS, reducers=2), 7)

    def test_reducer_with_no_input_counts_zero_and_finish_sums_parts(self):
        self.assertEqual(run_script(REDUCER, b"").decode().strip(), "distinct\t0")
        self.assertEqual(run_script(FINISH, b"distinct\t3\ndistinct\t0\ndistinct\t4\n")
                         .decode().strip(), "7")


class HadoopExactShippedFilesTests(unittest.TestCase):
    """The exact job runs with only the files its runner ships to Hadoop."""

    def test_mapper_and_reducer_run_in_a_folder_holding_only_the_shipped_files(self):
        runner = (HADOOP / "run-distinct-cluster.sh").read_text()
        modules = re.search(r'modules="([^"]+)"', runner).group(1)
        shipped = re.search(r'exact_files="([^"]+)"', runner).group(1)
        shipped = shipped.replace("$modules", modules).split(",")
        names = {"$script_dir": str(HADOOP), "$week7": str(WEEK7)}
        with tempfile.TemporaryDirectory() as task_dir:
            for entry in shipped:
                for var, value in names.items():
                    entry = entry.replace(var, value)
                shutil.copy(entry, task_dir)
            # Hadoop runs each script from the task folder, like this.
            mapped = subprocess.run(
                [sys.executable, "-I", "exact_distinct_mapper.py"],
                input=PARTS[0], cwd=task_dir, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=True).stdout
            reduced = subprocess.run(
                [sys.executable, "-I", "exact_distinct_reducer.py"],
                input=b"".join(sorted(mapped.splitlines(keepends=True))), cwd=task_dir,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout
        self.assertEqual(reduced.decode().strip(), "distinct\t4")


if __name__ == "__main__":
    unittest.main()
