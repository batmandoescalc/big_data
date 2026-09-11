# Apollo 11 transcript dataset

Three NASA transcripts give us real conversations to use for the Week 2
MapReduce word-count exercise. They cover communication with Mission Control,
public mission commentary, and voices recorded aboard the command module.

## Sources and snapshot

Downloaded on September 11, 2026, from NASA's
[Apollo 11 transcript collection](https://www.nasa.gov/wp-content/uploads/static/history/alsj/a11/a11trans.html).
NASA's index states that no copyright is asserted for these raw transcripts.
This snapshot uses those transcripts, rather than the separately corrected
Lunar Surface Journal text.

| Text file | Source | UTF-8 bytes | Whitespace tokens |
| --- | --- | ---: | ---: |
| `air-to-ground.txt` | [Technical air-to-ground transcript](https://www.nasa.gov/wp-content/uploads/static/history/alsj/a11/a11transcript_tec.html) | 837,054 | 172,961 |
| `public-commentary.txt` | [Public Affairs Office commentary](https://www.nasa.gov/wp-content/uploads/static/history/alsj/a11/a11transcript_pao.html) | 1,100,745 | 200,630 |
| `onboard-voice.txt` | [Command module voice transcript](https://www.nasa.gov/wp-content/uploads/static/history/alsj/a11/a11transscript_cm.html) | 283,577 | 65,813 |
| **Total** | | **2,221,376** | **439,404** |

Whitespace tokens include timestamps, speaker labels, and numbers. These totals
describe the input size; they are not results from our own word-count program.
At about 2.2 MB of text, this is a learning dataset, not a meaningful cluster
stress test.

## Preparation and reproducibility

From the repository root:

```bash
python3 scripts/fetch_apollo11.py
```

The script downloads just these three pages and saves a snapshot under
`data/apollo11/`, which Git ignores. Use `--output data/apollo11-another-date`
for a new snapshot; existing directories are never overwritten.

- `raw/`: original HTML bytes, retained for checking extraction results.
- `text/`: visible body text with HTML removed and whitespace normalized,
  saved as UTF-8.
- `manifest.json`: source URLs, retrieval times, byte counts, source encodings,
  and SHA-256 checksums identifying the exact raw and extracted files.

NASA's index has two links ending in `.htm` that returned 404 during collection;
the corresponding `.html` pages listed above worked. The air-to-ground and
onboard pages declared UTF-8 but contained legacy Windows-1252 bytes. The
downloader used strict Windows-1252 decoding for those pages and recorded that
choice in the manifest. The commentary page decoded as UTF-8.

The extraction preserves punctuation, case, timestamps, speaker labels,
document headers, and uncorrected OCR errors. Those details will affect word
counts. The later assignment can define how to handle them; the ingestion
script does not silently remove or correct them.

## HDFS layout

The verified snapshot location is `/datasets/apollo11/2026-09-11`, containing
the same `raw/`, `text/`, and `manifest.json` structure as the local snapshot.
Use only the `text/` directory as word-count input so that HTML and metadata
are not counted alongside the transcripts.

Upload verification passed on September 11, 2026: all seven files read back
with matching SHA-256 checksums. HDFS reported HEALTHY, two live replicas per
block, and zero missing, corrupt, or under-replicated blocks. The seven files
occupy 5,412,626 logical bytes including original HTML and the manifest.

After logging into the controller, enter the current Hadoop service-account
shell with `sudo -u hadoop bash -l`. Then inspect the input:

```bash
hdfs dfs -ls /datasets/apollo11/2026-09-11/text
hdfs dfs -cat /datasets/apollo11/2026-09-11/text/air-to-ground.txt | head -n 20
```

Our Python MapReduce word-count implementation has now run successfully on this
snapshot. See the [word-count walkthrough and results](../apollo11-wordcount.md).
