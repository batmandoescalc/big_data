import bz2
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "week-05" / "scripts"
MAPREDUCE = SCRIPTS / "mapreduce"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load("prepare_wikipedia", SCRIPTS / "prepare_wikipedia.py")
sys.modules["prepare_wikipedia"] = prepare
fetch = load("fetch_wikipedia", SCRIPTS / "fetch_wikipedia.py")
sqlite_benchmark = load("sqlite_benchmark", SCRIPTS / "sqlite_benchmark.py")
apollo_to_generic = load("apollo_to_generic", SCRIPTS / "apollo_to_generic.py")
verify_results = load("verify_results", SCRIPTS / "verify_results.py")
timer = load("shared_timer", ROOT / "common" / "benchmark" / "run_timed.py")


XML = """<?xml version="1.0" encoding="utf-8"?>
<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">
  <siteinfo><namespaces>
    <namespace key="0" />
    <namespace key="10">Template</namespace>
  </namespaces></siteinfo>
  <page><title>Moon</title><ns>0</ns><id>1</id><revision><id>11</id>
    <text>Hello\nMoon café</text></revision></page>
  <page><title>Template:A</title><ns>10</ns><id>2</id><revision><id>12</id>
    <text>One\ttwo three</text></revision></page>
  <page><title>Malformed</title><ns>0</ns><revision><text>missing id</text></revision></page>
</mediawiki>
"""


def run_script(path, data, *args, check=True):
    return subprocess.run(
        [sys.executable, str(path), *map(str, args)],
        input=data,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=check,
    )


class WikipediaPreparationTests(unittest.TestCase):
    def test_download_verifies_checksum_and_existing_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.bz2"
            source.write_bytes(b"verified content")
            destination = root / "downloads"
            destination.mkdir()
            part = {
                "name": "part.bz2",
                "url": source.as_uri(),
                "bytes": source.stat().st_size,
                "sha1": hashlib.sha1(source.read_bytes()).hexdigest(),
            }
            downloaded = fetch.download(part, destination)
            self.assertEqual(downloaded.read_bytes(), source.read_bytes())
            downloaded.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "does not match manifest"):
                fetch.download(part, destination)

    def test_dump_part_selection_is_ordered_and_bounded(self):
        status = {
            "jobs": {
                "articles": {
                    "files": {
                        "enwiki-pages-articles-multistream2.xml-p3p4.bz2": {
                            "url": "/two.bz2", "size": 60, "sha1": "b"
                        },
                        "enwiki-pages-articles-multistream1.xml-p10p20.bz2": {
                            "url": "/later.bz2", "size": 60, "sha1": "c"
                        },
                        "enwiki-pages-articles-multistream1.xml-p1p2.bz2": {
                            "url": "/one.bz2", "size": 50, "sha1": "a"
                        },
                        "enwiki-pages-articles-multistream-index.txt.bz2": {
                            "url": "/index.bz2", "size": 2
                        },
                    }
                }
            }
        }
        selected = fetch.select_parts(status, 100)
        self.assertEqual([part["name"] for part in selected], [
            "enwiki-pages-articles-multistream1.xml-p1p2.bz2"
        ])

    def test_size_parser(self):
        self.assertEqual(prepare.parse_size("2MiB"), 2 * 1024 * 1024)
        self.assertEqual(prepare.parse_size("128"), 128)
        with self.assertRaises(Exception):
            prepare.parse_size("2MB")

    def test_streaming_unicode_multiline_and_record_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "fixture.xml.bz2"
            source.write_bytes(bz2.compress(XML.encode("utf-8")))
            outputs = prepare.prepare([source], root / "out", [80, 10_000], "fixture")
            small = (outputs[0] / "pages.tsv").read_text(encoding="utf-8")
            large = (outputs[1] / "pages.tsv").read_text(encoding="utf-8")
            self.assertIn("Hello Moon café", large)
            self.assertIn("One two three", large)
            self.assertNotIn("\nMoon café", large)
            self.assertTrue(large.startswith(small))
            second_outputs = prepare.prepare(
                [source], root / "out-again", [80, 10_000], "fixture"
            )
            self.assertEqual(
                hashlib.sha256(large.encode("utf-8")).hexdigest(),
                hashlib.sha256(
                    (second_outputs[1] / "pages.tsv").read_bytes()
                ).hexdigest(),
            )
            manifest = json.loads((outputs[1] / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["page_rows"], 2)
            self.assertEqual(manifest["output_rows"], 2)
            self.assertEqual(manifest["malformed_pages"], 1)
            self.assertFalse(manifest["complete"])
            self.assertTrue(manifest["source_exhausted"])
            dimensions = (outputs[1] / "namespaces.tsv").read_text(encoding="utf-8")
            self.assertIn("0\t(main)\n", dimensions)
            self.assertIn("10\tTemplate\n", dimensions)

    def test_malformed_xml_is_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, contents in enumerate(("<mediawiki><page>", "")):
                source = root / f"bad-{index}.xml"
                source.write_text(contents, encoding="utf-8")
                with self.subTest(contents=contents), self.assertRaisesRegex(
                    ValueError, "malformed XML"
                ):
                    prepare.prepare([source], root / f"out-{index}", [100], "bad")

    def test_refuses_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "out").mkdir()
            with self.assertRaises(FileExistsError):
                prepare.prepare([root / "missing.xml"], root / "out", [100])


class RelationalPipelineTests(unittest.TestCase):
    def test_apollo_adapter_reports_and_excludes_unmatched_speakers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            speakers = root / "speakers.tsv"
            utterances = root / "utterances.tsv"
            speakers.write_text(
                "speaker_code\tcategory\tdescription\nCDR\tcrew\tCommander\n",
                encoding="utf-8",
            )
            utterances.write_text(
                "utterance_id\tmission_time\tspeaker_code\ttext\tword_count\n"
                "1\t001:00:00\tCDR\tKnown speaker\t2\n"
                "2\t001:00:01\tUNK\tUnknown speaker\t2\n",
                encoding="utf-8",
            )
            summary = apollo_to_generic.convert(utterances, speakers, root / "out")
            self.assertEqual(summary["input_rows"], 2)
            self.assertEqual(summary["matched_rows"], 1)
            self.assertEqual(summary["unmatched_rows"], 1)
            self.assertEqual(summary["unmatched_speaker_codes"], ["UNK"])
            facts = (root / "out" / "pages.tsv").read_text(encoding="utf-8")
            self.assertIn("\tCDR\t", facts)
            self.assertNotIn("\tUNK\t", facts)

    def make_relations(self, root):
        facts = root / "pages.tsv"
        dimensions = root / "namespaces.tsv"
        facts.write_text(
            "record_id\tdimension_key\tword_count\ttext_bytes\ttext\n"
            "1\t0\t3\t15\tHello Moon café\n"
            "2\t10\t3\t13\tOne two three\n"
            "3\t0\t2\t10\tHello again\n",
            encoding="utf-8",
        )
        dimensions.write_text(
            "dimension_key\tcategory\n0\t(main)\n10\tTemplate\n",
            encoding="utf-8",
        )
        return facts, dimensions

    def test_map_side_join_and_aggregation_match_sqlite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            facts, dimensions = self.make_relations(root)
            mapped = run_script(
                MAPREDUCE / "map_join_aggregate.py",
                facts.read_text(encoding="utf-8"),
                dimensions,
            ).stdout
            reduced = run_script(
                MAPREDUCE / "aggregate_reducer.py",
                "\n".join(sorted(mapped.splitlines())) + "\n",
            ).stdout
            sqlite_output = root / "sqlite.tsv"
            sqlite_benchmark.run(facts, dimensions, root / "fixture.db", sqlite_output)
            hadoop_output = root / "hadoop.tsv"
            hadoop_output.write_text(reduced, encoding="utf-8")
            verify_results.verify(sqlite_output, hadoop_output)
            self.assertEqual(
                reduced,
                "(main)\t2\t5\t25\nTemplate\t1\t3\t13\n",
            )

    def test_unknown_dimension_fails_instead_of_dropping_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, dimensions = self.make_relations(root)
            completed = run_script(
                MAPREDUCE / "map_join_aggregate.py",
                "record_id\tdimension_key\tword_count\ttext_bytes\ttext\n"
                "9\t999\t1\t4\ttest\n",
                dimensions,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("unknown dimension key", completed.stderr)

    def test_reducer_combines_partial_aggregates(self):
        reduced = run_script(
            MAPREDUCE / "aggregate_reducer.py",
            "crew\t2\t10\t20\ncrew\t3\t15\t30\n",
        ).stdout
        self.assertEqual(reduced, "crew\t5\t25\t50\n")


class TimingTests(unittest.TestCase):
    def test_versioned_record_and_counter_parsing(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "run.json"
            status = timer.timed_run(
                "fixture",
                manifest,
                [
                    sys.executable,
                    "-c",
                    "print('application_123_0001\\nCPU time spent (ms)=17\\nMap input records=3')",
                ],
                engine="fixture",
                dataset_id="tiny",
                input_rows=3,
                input_bytes=30,
                output_rows=1,
            )
            record = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(status, 0)
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["application_ids"], ["application_123_0001"])
            self.assertEqual(record["hadoop_counters"]["cpu_time_ms"], 17)
            self.assertEqual(record["hadoop_counters"]["map_input_records"], 3)

    def test_failure_status_is_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "failure.json"
            status = timer.timed_run(
                "intentional-failure",
                manifest,
                [sys.executable, "-c", "raise SystemExit(7)"],
                engine="fixture",
                dataset_id="tiny",
            )
            record = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(status, 7)
            self.assertEqual(record["exit_status"], 7)
            self.assertGreaterEqual(record["elapsed_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
