# Week 3: Relational Operations in SQL and Hadoop

## Objectives

Week 3 applies the relational-algebra ideas from Section 2.3 of *Mining of
Massive Datasets* to the Apollo 11 data prepared in Week 2. The work covers:

- A natural join between transcript utterances and speaker metadata.
- Grouping by speaker category.
- `COUNT(*)` and `SUM(word_count)` aggregations.
- The same calculation in SQLite and Hadoop Streaming.
- Wall-clock timing and exact output comparison.
- A Section 2.4 investigation of Spark and TensorFlow.

This is a small-data correctness experiment. It is not a performance benchmark
and does not show that SQLite is generally faster than a distributed system.

## Relational data

The NASA air-to-ground transcript has timestamp-and-speaker headers followed by
spoken text. [prepare_relations.py](scripts/prepare_relations.py) converts it
into two tab-separated relations:

| Relation | Columns |
| --- | --- |
| `utterances` | utterance ID, mission time, speaker code, word count, text |
| `speakers` | speaker code, category, description |

The September 23 snapshot produced 8,430 utterance rows and 12 speaker rows.
Ten utterances use four labels not present in the selected NASA speaker lookup:
`CDF`, `CMP/LMP`, `PRESIDENT`, and `SWIM`. They remain in the input and are
reported as unmatched instead of being silently corrected. Ten timestamp-like
headers containing apparent `O`/`0` transcription errors are also reported in
the generated manifest rather than guessed.

Generated datasets and run evidence live under the ignored `data/` directory.
They are reproducible and are not committed to Git.

## SQL version

[sqlite_baseline.py](scripts/sqlite_baseline.py) uses Python's standard
`sqlite3` module. It creates the tables in memory, loads both TSV files, and
runs the equivalent of:

```sql
SELECT s.category,
       COUNT(*) AS utterance_count,
       SUM(u.word_count) AS total_words
FROM utterances AS u
JOIN speakers AS s
  ON s.speaker_code = u.speaker_code
GROUP BY s.category
ORDER BY s.category;
```

The join keeps only rows whose speaker code occurs in both relations. Grouping
then collects the joined rows by speaker category and calculates the requested
aggregates.

## Hadoop version

The Hadoop implementation uses two streaming jobs:

1. **Natural join:** both mappers key records by speaker code and tag each row
   as speaker metadata or an utterance. The reducer combines records that share
   that key and emits enriched utterances.
2. **Grouping and aggregation:** the second mapper keys joined rows by category.
   The reducer counts utterances and sums their word counts.

Hadoop guarantees that values with the same key reach one reducer, but not the
order in which the values arrive. The first live attempt incorrectly assumed
speaker metadata would arrive before its utterances. It emitted only 4,705
joined rows. The reducer was changed to buffer values within each key group,
and a reversed-order regression test was added. The failed HDFS output was
retained; the corrected run used a new output path.

The successful run used:

- Input: `/datasets/apollo11/2026-09-23/relational`
- Output: `/results/apollo11/week03-relational-20260923T144500Z`
- Join application: `application_1790153547270_0003`
- Aggregation application: `application_1790153547270_0004`

The launcher refuses existing result directories, so it cannot overwrite an
earlier run.

## Results

| Speaker category | Utterances | Total words |
| --- | ---: | ---: |
| crew | 4,490 | 53,303 |
| mission-control | 3,884 | 61,246 |
| recovery | 11 | 66 |
| remote-site | 35 | 233 |

SQLite and Hadoop each produced 8,420 joined rows and four aggregate rows.
[verify_results.py](scripts/verify_results.py) sorts both outputs before
comparison because reducer value order is not meaningful. Both comparisons
matched exactly:

| Output | Canonical SHA-256 |
| --- | --- |
| Joined rows | `005dd1a568a42cd191c060df7907cbbc20b33709828021012b44d4e0fb9929ad` |
| Aggregates | `aa60fb72284e97b1a893282abaec961925abe28c6ad7a637db048963cfdc6d3e` |

## Runtime observations

[run_timed.py](scripts/run_timed.py) uses a monotonic clock and records UTC
start time, elapsed seconds, exit status, row counts, and YARN application IDs.

| Operation | Wall-clock time |
| --- | ---: |
| SQLite database load and queries | 0.042678 seconds |
| SQLite full command, including startup and file output | 0.197213 seconds |
| Hadoop natural join | 40.968471 seconds |
| Hadoop grouping and aggregation | 46.369373 seconds |
| Hadoop full two-job pipeline | 95.340955 seconds |

The Apollo input is only about one megabyte after conversion. Hadoop spends
most of this run starting JVMs, requesting YARN containers, scheduling tasks,
and shuffling data. SQLite runs in one local process. A meaningful scalability
comparison would require larger datasets, repeated trials, controlled hardware,
and separate measurements of loading, computation, and output.

## Section 2.4: Spark and TensorFlow

Spark generalizes the workflow beyond a fixed MapReduce pair. Its
transformations include `map`, `flatMap`, `filter`, joins, and grouping;
actions trigger lazy evaluation. RDD lineage records how data was produced so
lost partitions can be recomputed without storing every intermediate result.

The first useful Spark experiment would repeat this join and aggregation with
Spark DataFrames or RDDs, then compare the code and intermediate I/O with the
two Hadoop jobs. Later, Spark can support the study's distributed-clustering
work.

Spark is separate software, but it can use the current HDFS and YARN cluster;
another VM is not required. A future deployment should investigate the current
Spark 3.5 maintenance release because Spark 3.5 supports Java 11. Spark 4
requires Java 17, while this Hadoop 3.4.3 cluster currently uses Java 11. A
YARN deployment can distribute Spark libraries from an archive in HDFS rather
than requiring a permanent full installation on every worker. No Spark package
or cluster configuration was changed this week.

TensorFlow is designed around tensors and machine-learning operations. It is
not the clearest tool for this relational exercise. A later application could
classify transcript segments by speaker role or mission phase, but that would
require a carefully labeled dataset and a defined evaluation measure.

References:

- [Spark 3.5 overview](https://spark.apache.org/docs/3.5.6/)
- [Running Spark on YARN](https://spark.apache.org/docs/latest/running-on-yarn)

## Reproduction and tests

From the repository root:

```bash
python3 week-02/scripts/fetch_apollo11.py --output data/apollo11
python3 week-03/scripts/prepare_relations.py \
  --input data/apollo11/text/air-to-ground.txt \
  --output-dir data/week-03/relations
python3 week-03/scripts/sqlite_baseline.py \
  --utterances data/week-03/relations/utterances.tsv \
  --speakers data/week-03/relations/speakers.tsv \
  --output-dir data/week-03/sqlite
python3 -m unittest discover -s week-03/tests -v
```

The Hadoop launcher is intended for the controller and the `hadoop` service
account. It takes an existing HDFS input directory, a new result base, and the
expected utterance, matched, and aggregate row counts. It never provisions or
reconfigures the cluster.

## Responsible AI use

To avoid plausible-looking but unsupported work:

- Every program maps directly to a stated Week 3 objective or textbook idea.
- Raw data is preserved and generated relations are reproducible.
- Malformed and unmatched records are reported instead of silently invented.
- SQLite serves as an independent correctness oracle for Hadoop.
- Automated tests cover parsing, joins, aggregation, Unicode, malformed input,
  unknown speakers, immutability, timing, and reducer value ordering.
- A failed distributed run and its cause are documented rather than hidden.
- Performance claims are limited to the measured environment and dataset.
- AI-assisted code must be reviewed, tested, and understood before it is
  presented as course work.
