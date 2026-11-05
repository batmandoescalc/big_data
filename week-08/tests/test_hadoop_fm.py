"""The Hadoop FM job for pageviews gives the same answer as one process."""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import sys
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
HADOOP = SCRIPTS / "hadoop"
REDUCER = SCRIPTS.parents[1] / "week-07" / "scripts" / "hadoop" / "fm_reducer.py"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HADOOP))

from pageviews import HashedFM, key_hash, parse_line  # noqa: E402
from fm_finish import finish  # noqa: E402

PART_A = (b"en Main_Page 500 0\nen Cat 3 0\nde Hund 7 0\n"
          b"bad line\nfr Chat 2 0\n")
PART_B = (b"en Main_Page 410 0\nen Dog 1 0\nes Perro 4 0\nen Cat 9 0\n")


def run_script(path, data, *args):
    return subprocess.run([sys.executable, str(path), *args], input=data,
                          stdout=subprocess.PIPE, check=True).stdout


class HadoopFMPageviewsTests(unittest.TestCase):
    """Mapper, shuffle sort, reducer and finish step match a single sketch."""

    def test_two_partitions_merge_to_single_process_registers(self):
        mapped = run_script(HADOOP / "fm_pageviews_mapper.py", PART_A, "4")
        mapped += run_script(HADOOP / "fm_pageviews_mapper.py", PART_B, "4")
        # Hadoop sorts mapper output by key before the reducer sees it.
        shuffled = b"".join(sorted(mapped.splitlines(keepends=True)))
        reduced = run_script(REDUCER, shuffled).decode()

        single = HashedFM(4)
        for line in (PART_A + PART_B).splitlines():
            parsed = parse_line(line)
            if parsed:
                single.add_hash(key_hash(parsed[0]))

        merged = finish(reduced.splitlines(), 4)
        self.assertEqual(merged.registers, single.registers)
        self.assertEqual(merged.estimate(), single.estimate())

    def test_mapper_skips_malformed_lines_and_emits_only_touched_registers(self):
        out = run_script(HADOOP / "fm_pageviews_mapper.py",
                         b"not a pageview line\n", "4")
        self.assertEqual(out, b"")


class HadoopShippedFilesTests(unittest.TestCase):
    """The mapper runs with only the files the runner ships to Hadoop."""

    def test_mapper_runs_in_a_folder_holding_only_the_shipped_files(self):
        runner = (HADOOP / "run-fm-pageviews-local.sh").read_text()
        shipped = re.search(r'-files "([^"]+)"', runner).group(1).split(",")
        names = {"$script_dir": str(HADOOP), "$week7": str(REDUCER.parents[1])}
        with tempfile.TemporaryDirectory() as task_dir:
            for entry in shipped:
                for var, value in names.items():
                    entry = entry.replace(var, value)
                shutil.copy(entry, task_dir)
            # Hadoop runs the mapper from the task folder, like this.
            out = subprocess.run(
                [sys.executable, "-I", "fm_pageviews_mapper.py", "4"],
                input=PART_A, cwd=task_dir, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=True).stdout
        self.assertTrue(out.strip())


if __name__ == "__main__":
    unittest.main()
