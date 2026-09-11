# Our Apollo 11 word count

We wrote the mapper and reducer in Python. Hadoop reads the files from HDFS,
runs mapper tasks, groups matching words, and sends those groups to our reducer.
YARN supplies the cluster resources for the job.

For `Houston Houston Eagle`:

1. **Map:** emit `houston\t1`, `houston\t1`, and `eagle\t1`.
2. **Group:** Hadoop brings the two `houston` records together.
3. **Reduce:** add each word's counts, producing `eagle\t1` and `houston\t2`.

`\t` represents a tab separating the word from its count.

## What counts as a word

- Convert text to lowercase. Count runs of English letters `a` through `z`.
- Keep apostrophes inside words: `you're` is one word. Normalize curly `’`
  to straight `'` first.
- Other characters separate words: `air-to-ground` becomes three words,
  `Apollo 11` becomes `apollo`, and `A11B` becomes `a` and `b`.
- Count speaker labels, headers, and common words such as `the`. Preserve OCR
  mistakes. This counts the extracted documents, not just spoken dialogue.

## Read the program

- [mapper.py](../scripts/wordcount/mapper.py) reads one line at a time, finds
  words, and prints each word with a count of one.
- [reducer.py](../scripts/wordcount/reducer.py) reads words in sorted order.
  When the word changes, it prints the previous word's total and starts a new
  total. It prints the last total after the loop ends.
- [run-hadoop.sh](../scripts/wordcount/run-hadoop.sh) submits the programs using
  [Hadoop Streaming](https://hadoop.apache.org/docs/r3.4.3/hadoop-streaming/HadoopStreaming.html).
  `-files` distributes our scripts to task containers. One reducer makes the
  final output easy to inspect. We do not use a combiner in this first version.

Neither Python program loads the entire dataset into memory. The reducer only
holds the current word and its running total.

## Try the small example locally

From the repository root, in Bash:

```bash
set -o pipefail
printf 'Houston Houston Eagle\n' \
  | python3 week-02/scripts/wordcount/mapper.py \
  | LC_ALL=C sort \
  | python3 week-02/scripts/wordcount/reducer.py
python3 -m unittest discover -s week-02/tests -p 'test_wordcount.py' -v
```

Expected output is `eagle: 1` and `houston: 2`, separated by tabs in the file.
Local `sort` stands in for Hadoop's grouping step; this local pipeline does
not use the cluster.

## Run on Hadoop

Copy the three files in `week-02/scripts/wordcount/` into one directory on the
controller, then run as the `hadoop` service account:

```bash
bash run-hadoop.sh /results/apollo11/wordcount-UNIQUE-RUN-NAME
```

Choose a new output path each time. Existing output is refused. The input is
always `/datasets/apollo11/2026-09-11/text`, so originals and metadata are
excluded. Python 3 must be installed on each worker.

After success, read the output from the controller:

```bash
source /etc/profile.d/hadoop.sh
hdfs dfs -cat '/results/apollo11/wordcount-UNIQUE-RUN-NAME/part-*'
```

This 2.2 MB dataset demonstrates MapReduce execution. It does not measure
large-scale performance; job startup can take longer than counting the text.

## Verified run: September 11, 2026

Job `job_1789157262378_0002` completed successfully through YARN with three
launched mapper tasks and one reducer. It read 2,221,376 input bytes, emitted
355,040 word occurrences, and produced 8,184 distinct word totals. Hadoop's
counts agree with the downloaded output. The job counters also recorded one
killed map task and zero failed shuffles; the cause of that killed-task counter
was not investigated because the job succeeded and every final count matched.

An independent local reference scanned characters and counted words with
Python's `Counter`, without importing either program or using the mapper's
regular expression. Every word and count matched exactly.

| Word | Count |
| --- | ---: |
| the | 16,597 |
| houston | 4,487 |
| apollo | 3,808 |
| eagle | 1,655 |
| tranquility | 739 |
| moon | 303 |

HDFS output:
`/results/apollo11/wordcount-20260911T203041Z-81724750`

Local output and verification summary:
`data/apollo11/results/20260911T203041Z-81724750/`
(`counts.tsv`, `run.json`, and `verification.json`, ignored by Git).
The run manifest records the SHA-256 hashes of the submitted programs.
The counts file SHA-256 is
`e2320508df9dd7ff1293765105112c246975aec29417828c0ea77518a2332ed9`.

Five new tests cover known totals, word rules, empty input, adding partial
counts, and rejecting invalid counts. All 20 repository tests passed.
