"""Unit and integration tests for the Week 3 relational pipeline."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


WEEK = Path(__file__).resolve().parents[1]
SCRIPTS = WEEK / "scripts"
MAPREDUCE = SCRIPTS / "mapreduce"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load_module("prepare_relations", SCRIPTS / "prepare_relations.py")
sqlite_baseline = load_module("sqlite_baseline", SCRIPTS / "sqlite_baseline.py")
verify_results = load_module("verify_results", SCRIPTS / "verify_results.py")


def run_script(name, input_text):
    return subprocess.run(
        [sys.executable, str(MAPREDUCE / name)],
        input=input_text,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )


def local_join(utterances_tsv, speakers_tsv):
    mapped = run_script("join_mapper.py", utterances_tsv + speakers_tsv).stdout
    grouped = "\n".join(sorted(mapped.splitlines())) + "\n"
    return run_script("join_reducer.py", grouped).stdout


def local_aggregate(joined_tsv):
    mapped = run_script("aggregate_mapper.py", joined_tsv).stdout
    grouped = "\n".join(sorted(mapped.splitlines())) + "\n"
    return run_script("aggregate_reducer.py", grouped).stdout


class ParserTests(unittest.TestCase):
    def test_multiline_inline_unicode_and_metadata(self):
        text = """INTRODUCTION
00 00 00 04 CDR Inline start
Second line with you’re here.
(GOSS NET 1) Tape 1/2 Page 2
00 00 01 02 CC
Apollo 11, Houston.
"""
        records, malformed = prepare.parse_transcript(text)
        self.assertEqual(malformed, [])
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["speaker_code"], "CDR")
        self.assertEqual(records[0]["text"], "Inline start Second line with you’re here.")
        self.assertEqual(records[0]["word_count"], 7)
        self.assertEqual(records[1]["mission_time"], "00:00:01:02")

    def test_malformed_timestamp_is_reported_and_not_attached(self):
        text = """00 00 00 04 CDR
Good record.
00 O0 08 19 CC
Should not join the previous record.
00 00 09 00 CC
MARK.
"""
        records, malformed = prepare.parse_transcript(text)
        self.assertEqual(len(records), 2)
        self.assertEqual(len(malformed), 1)
        self.assertEqual(records[0]["text"], "Good record.")
        self.assertEqual(records[1]["text"], "MARK.")

    def test_tabs_and_newlines_are_normalized(self):
        self.assertEqual(prepare.sanitize(" one\t two   three "), "one two three")


class MapReduceTests(unittest.TestCase):
    def setUp(self):
        self.utterances = (
            "record_type\tutterance_id\tmission_time\tspeaker_code\tword_count\ttext\n"
            "U\tu-1\t00:00:00:01\tCDR\t2\tHello moon\n"
            "U\tu-2\t00:00:00:02\tCC\t3\tHello Apollo eleven\n"
            "U\tu-3\t00:00:00:03\tZZ\t1\tUnknown\n"
        )
        self.speakers = (
            "record_type\tspeaker_code\tcategory\tdescription\n"
            "S\tCDR\tcrew\tCommander\n"
            "S\tCC\tmission-control\tCapsule communicator\n"
        )

    def test_join_uses_shared_speaker_code_and_omits_unknown(self):
        joined = local_join(self.utterances, self.speakers)
        self.assertEqual(
            joined,
            "u-2\t00:00:00:02\tCC\tmission-control\t3\tHello Apollo eleven\n"
            "u-1\t00:00:00:01\tCDR\tcrew\t2\tHello moon\n",
        )

    def test_grouping_counts_and_sums(self):
        joined = local_join(self.utterances, self.speakers)
        self.assertEqual(
            local_aggregate(joined),
            "crew\t1\t2\nmission-control\t1\t3\n",
        )

    def test_join_does_not_assume_metadata_value_arrives_first(self):
        mapped = (
            "CDR\tU\tu-1\t00:00:00:01\t2\tHello moon\n"
            "CDR\tS\tcrew\tCommander\n"
        )
        self.assertEqual(
            run_script("join_reducer.py", mapped).stdout,
            "u-1\t00:00:00:01\tCDR\tcrew\t2\tHello moon\n",
        )

    def test_mapper_rejects_invalid_input(self):
        with self.assertRaises(subprocess.CalledProcessError):
            run_script("join_mapper.py", "bad\trecord\n")


class EndToEndTests(unittest.TestCase):
    def test_sqlite_and_streaming_results_match(self):
        transcript = """00 00 00 04 CDR
Hello moon.
00 00 01 02 CC
Hello Apollo eleven.
00 00 01 05 ZZ
Unknown speaker.
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "transcript.txt"
            source.write_text(transcript, encoding="utf-8")
            relations = root / "relations"
            manifest = prepare.prepare(source, relations)
            self.assertEqual(manifest["unknown_speaker_codes"], ["ZZ"])
            sql_output = root / "sql"
            sqlite_baseline.run(
                relations / "utterances.tsv", relations / "speakers.tsv", sql_output
            )
            utterances = (relations / "utterances.tsv").read_text(encoding="utf-8")
            speakers = (relations / "speakers.tsv").read_text(encoding="utf-8")
            joined = local_join(utterances, speakers)
            aggregated = local_aggregate(joined)
            self.assertEqual(joined, (sql_output / "joined.tsv").read_text(encoding="utf-8"))
            self.assertEqual(
                aggregated,
                (sql_output / "aggregates.tsv").read_text(encoding="utf-8"),
            )
            hadoop_output = root / "hadoop"
            hadoop_output.mkdir()
            # Reverse join lines to prove comparison is independent of reducer order.
            (hadoop_output / "joined.tsv").write_text(
                "\n".join(reversed(joined.splitlines())) + "\n", encoding="utf-8"
            )
            (hadoop_output / "aggregates.tsv").write_text(
                aggregated, encoding="utf-8"
            )
            self.assertEqual(
                verify_results.verify(sql_output, hadoop_output)["status"], "match"
            )

    def test_output_directories_are_immutable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "transcript.txt"
            source.write_text("00 00 00 04 CDR\nHello.\n", encoding="utf-8")
            output = root / "relations"
            prepare.prepare(source, output)
            with self.assertRaises(ValueError):
                prepare.prepare(source, output)


class TimingTests(unittest.TestCase):
    def test_timing_wrapper_records_success_and_application_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "runtime.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "run_timed.py"),
                    "--label",
                    "fixture",
                    "--manifest",
                    str(manifest),
                    "--input-rows",
                    "3",
                    "--output-rows",
                    "1",
                    "--",
                    sys.executable,
                    "-c",
                    "print('application_123_0001')",
                ],
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=True,
            )
            record = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertIn("application_123_0001", completed.stdout)
            self.assertEqual(record["application_ids"], ["application_123_0001"])
            self.assertEqual(record["exit_status"], 0)
            self.assertGreaterEqual(record["elapsed_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
