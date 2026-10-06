# Week 5: Scaling, Join Design, and Runtime Investigation

## Purpose and current status

Week 5 turns the small Week 3 correctness experiment into a scaling study. It
asks why SQLite completed the Apollo query in a fraction of a second while the
original two-job Hadoop pipeline took about 95 seconds, whether that gap changes
as input grows, and whether Spark is likely to help.

The implementation, local validation, and live one-job Apollo validation are
complete. The Wikipedia timing matrix is in progress on the cluster. No timing
values are published before their preserved run records exist. The read-only
preflight passed with three HDFS workers, three YARN workers, healthy HDFS,
replication two, and sufficient capacity.

## What changed from Week 3

### Why the first reducer needed a buffer

MMDS Section 2.3.7 describes a reduce-side natural join: both relations are
keyed by their shared attribute, and a reducer receives all records for one
key. Hadoop sorts **keys**, but it does not promise that the dimension record
will arrive before the fact records within that key group.

The first Week 3 reducer processed utterances before it had seen their speaker
metadata, so it emitted only 4,705 joined rows. The corrected reducer buffered
the utterances until it found the metadata. That correction was logically
successful: it produced all 8,420 matched rows, and both joined rows and final
aggregates matched SQLite exactly.

The remaining design problem is scale. If millions of fact rows share one
popular key, buffering the whole key group can exhaust one reducer's memory.
This is consistent with the reducer-size and communication-cost concerns in
MMDS Section 2.6.

### New map-side replicated join

The Week 5 pipeline uses the pattern appropriate for a tiny dimension table:

1. Hadoop's distributed cache places the dimension TSV beside every mapper.
2. Each mapper loads that small lookup table into memory once.
3. Each fact row is joined immediately, then emitted as category plus numeric
   measures.
4. A combiner and reducer sum page/utterance count, words, and text bytes.

This removes the unbounded fact-row buffer, the separate join reducer, and the
intermediate HDFS dataset. It is not a universal replacement: a large-to-large
join still needs partitioning or a reduce-side strategy because a large
dimension cannot safely be copied into every mapper.

Unknown dimension keys fail the mapper instead of disappearing silently.
During Apollo adaptation, the previously documented 10 unmatched input rows
are counted and reported before the strict join input is written.

## Apollo validation

The authentic Week 3 relations were converted to the generic Week 5 schema.
The adapter reported 8,430 source utterances, 8,420 matched records, and 10
unmatched records using `CDF`, `CMP/LMP`, `PRESIDENT`, or `SWIM`.

The local map-side pipeline processed the 8,420 matched records in 0.243
seconds. This is a development-machine validation time, not a Hadoop result.
The live cluster then executed the one-job design through YARN. Its output
matched SQLite byte-for-byte after canonical sorting:

| Category | Records | Words | Text bytes |
| --- | ---: | ---: | ---: |
| crew | 4,490 | 53,303 | 296,357 |
| mission-control | 3,884 | 61,246 | 352,411 |
| recovery | 11 | 66 | 424 |
| remote-site | 35 | 233 | 1,350 |

This reproduces the four Week 3 count/word totals while removing the reducer
buffer and one distributed job.

| Apollo operation | Wall-clock time |
| --- | ---: |
| SQLite generic query | 0.105507 seconds |
| One-job map-side Hadoop query | 46.585714 seconds |
| Historical two-job Week 3 Hadoop pipeline | 95.340955 seconds |

The new live job used two mappers, one reducer, and a combiner. Its 8,420 map
outputs were combined into only seven reducer input records across four groups.
The observed wall time is about 51% lower than the earlier two-job run, which
is consistent with removing a YARN submission and intermediate HDFS I/O.
Because these runs occurred at different times, the difference is useful
evidence for the redesign but not a controlled universal speedup claim.

## Wikipedia data and provenance

The source is the English Wikipedia `pages-articles-multistream` split dump
dated October 1, 2026 and completed October 2. The pinned machine-readable
manifest is:

`https://dumps.wikimedia.org/enwiki/20261001/dumpstatus.json`

It identifies 71 split article archives totaling 26,899,623,591 compressed
bytes (25.05 GiB), with source URLs and SHA-1 values. The downloader verifies
size and SHA-1 before accepting each file. The preparation program also
records a local SHA-256 for every source part used.

The parser reads bzip2 streams directly instead of materializing a giant XML
file. It creates two generic relations:

| Relation | Columns |
| --- | --- |
| `pages.tsv` | record ID, namespace ID, word count, UTF-8 text bytes, text |
| `namespaces.tsv` | namespace ID, namespace name |

Tabs and line breaks are normalized, Unicode is preserved, malformed XML stops
the run, and incomplete page records are counted. Each larger sample begins
with every complete record in each smaller sample; records are never repeated
to manufacture scale.

Planned immutable samples:

| Target | SQLite runs | Hadoop runs | Current status |
| --- | ---: | ---: | --- |
| 2 MiB | 3 | 3 | awaiting cluster/network |
| 128 MiB | 3 | 3 | awaiting cluster/network |
| 1 GiB | 3 | 3 | awaiting cluster/network |
| 10 GiB | 3 | 3 | awaiting cluster/network |
| 100 GiB | 0 or 3 after disk preflight | 3 | awaiting cluster/network |

Preparation/download time is recorded separately from query time.

## Identical query in both engines

SQLite and Hadoop both perform an equality join from each fact's namespace ID
to the namespace table, group by namespace name, and compute:

- page count;
- total word count;
- total UTF-8 text bytes.

SQLite uses Python's built-in `sqlite3`. Hadoop Streaming uses the replicated
map-side join plus one aggregation job. Outputs are normalized and must match
exactly for every size where both engines run.

## Timing method

[`common/benchmark/run_timed.py`](../common/benchmark/run_timed.py) is the one
versioned timing recorder used by the Week 3 launcher, the Week 4 launcher, and
all Week 5 commands. It uses Python's monotonic performance clock and writes
JSON containing engine, dataset ID, input rows/bytes, UTC start, elapsed time,
exit status, output rows, application/job IDs, and selected Hadoop counters.

The first run is retained explicitly because it includes cold-start effects.
Three attempts are made per engine/size, and
[`summarize_runs.py`](scripts/summarize_runs.py) reports the median of successful
runs. Operating-system caches are not cleared. The comparison therefore shows
observed first/repeated behavior, not an artificial cold-cache laboratory test.

The original approximately 95-second Week 3 Hadoop result is explained by two
YARN submissions, container/JVM/Python startup, two shuffle/sort phases, an
intermediate HDFS write/read, and only one reducer per job. A 2.2 MB input
contains too little work to amortize those fixed costs. The Week 5 curve is
designed to separate that startup floor from throughput at larger sizes.

### Runtime results

No Wikipedia timing table is published yet. The live cluster preflight passed
on October 6, 2026, and the pinned dump pipeline is running. Results will be
inserted only from preserved JSON manifests after the required runs succeed.

## Cluster safety and reproduction

The benchmark does not provision machines or change Hadoop configuration.
Before staging data, [`preflight-cluster.sh`](scripts/preflight-cluster.sh)
requires three live HDFS workers, three live YARN workers, a healthy filesystem,
replication factor two, and 25% capacity headroom above two replicas of the
planned logical input.

Once connected to the approved network, download and normalize on the mounted
data drive rather than the small root filesystem:

```bash
python3 week-05/scripts/fetch_wikipedia.py \
  --status-url https://dumps.wikimedia.org/enwiki/20261001/dumpstatus.json \
  --output-dir /data/week-05/wikipedia-source \
  --max-compressed 30GiB

python3 week-05/scripts/prepare_wikipedia.py \
  --source-manifest /data/week-05/wikipedia-source/source-manifest.json \
  --output-root /data/week-05/samples \
  --snapshot 20261001 \
  --target 2MiB --target 128MiB --target 1GiB \
  --target 10GiB --target 100GiB
```

Then run the complete matrix from the repository root:

```bash
bash week-05/scripts/run-benchmark-matrix.sh \
  /data/week-05/samples \
  /datasets/wikipedia/20261001/week05 \
  /results/wikipedia/week05-UNIQUE-RUN-ID \
  /data/week-05/runtime/UNIQUE-RUN-ID
```

All HDFS inputs/outputs must be new. Inputs are uploaded with replication two;
the runner preserves all prior Week 2–4 paths. The 100 GiB SQLite attempt is
skipped with an explicit reason if five input-size equivalents of local free
space are unavailable.

## Spark estimate

Spark is not installed this week. It would probably reduce the current
two-job Hadoop time for a multi-stage pipeline because executors can be reused,
the tiny namespace table can be broadcast, and an intermediate result need not
be written to HDFS. The new one-job Hadoop design already removes much of that
avoidable work, so Spark's advantage must be measured rather than assumed.

A cold Spark-on-YARN job still starts a driver and executors and is unlikely to
beat SQLite on 2 MiB. A later experiment should use Spark 3.5.7, which can run
on the existing YARN/Java 11 environment and distribute a cached Spark archive
from HDFS. Another VM is not required.

- [Wikimedia dump index](https://dumps.wikimedia.org/enwiki/latest/)
- [Wikimedia dump size guidance](https://meta.wikimedia.org/wiki/Data_dumps/Dumps_sizes_and_growth)
- [Spark 3.5.7 on YARN](https://spark.apache.org/docs/3.5.7/running-on-yarn.html)

## Tests

Week 5 tests cover XML/bzip2 streaming, Unicode, malformed records, immutable
outputs, deterministic nested samples, dump-part selection, Apollo adaptation,
strict unknown-key behavior, aggregation, SQL/streaming equality, successful
and failed timer records, and Hadoop-counter parsing.

```bash
python3 -m unittest discover -s week-05/tests -v
```

All 12 Week 5 tests pass locally. Week 3's 10 tests also pass. Some older Week
2/4 tests rely on Unix-only modules, symlinks, and UTF-8 process defaults, so
their complete regression run must be repeated on the Linux controller rather
than interpreted as Windows algorithm failures.

Generated dumps, TSVs, SQLite databases, timing logs, private access details,
and cluster identifiers remain ignored by Git.
