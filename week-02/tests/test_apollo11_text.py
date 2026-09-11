import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "fetch_apollo11", Path(__file__).resolve().parents[1] / "scripts/fetch_apollo11.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TranscriptTextTests(unittest.TestCase):
    def extract(self, html):
        parser = module.VisibleText()
        parser.feed(html)
        parser.close()
        return parser.text()

    def test_removes_page_metadata_and_scripts(self):
        text = self.extract('<head><title>Ignore</title></head><body>Hello<script>tracking()</script>'
                            '<style>.ignore{}</style><br>world</body>Outside')
        self.assertEqual(text, "Hello\nworld\n")

    def test_preserves_speaker_time_and_punctuation(self):
        text = self.extract('<body>00 00 01 02 <font>CC</font><br>Test &amp; test!<br>0123</body>')
        self.assertEqual(text, "00 00 01 02 CC\nTest & test!\n0123\n")

    def test_separates_table_cells_and_inline_words(self):
        text = self.extract('<body><table><tr><td>CDR</td><td>Commander</td></tr></table>'
                            '<p>A <b>small</b> sample.</p></body>')
        self.assertEqual(text, "CDR Commander\nA small sample.\n")

    def test_legacy_encoding_is_recorded_without_replacement_characters(self):
        text, encoding = module.decode_source(b"Sample \xa2 text", "utf-8")
        self.assertEqual(text, "Sample ¢ text")
        self.assertEqual(encoding, "windows-1252")


if __name__ == "__main__":
    unittest.main()
