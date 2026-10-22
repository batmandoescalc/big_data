# Repository Guide: Topics, Functions, and Results

This page is the cross-week map of the independent study. Each weekly README
contains the full explanation, commands, evidence, and limitations.

## Study outline

| Week | Topic | Main question |
| --- | --- | --- |
| 1 | Distributed storage and MapReduce | Why split storage and computation across machines? |
| 2 | Hadoop and word count | Can the four-node cluster store data and run a verified distributed job? |
| 3 | Relational operations | Can Hadoop reproduce SQL joins, grouping, and aggregation exactly? |
| 4 | Similar-item search | Can minhash and LSH find replayed transcript passages without comparing every pair? |
| 5 | Scaling and join design | When does Hadoop's fixed overhead become small relative to useful work? |
| 6 | Midsemester checkpoint | Can a new reader find, run, and understand the accumulated work? |

## Architecture and data flow

The controller runs the HDFS NameNode and YARN ResourceManager. Three workers
run HDFS DataNodes and YARN NodeManagers. HDFS divides and replicates files;
YARN schedules the mapper and reducer processes close to that data.

Typical experiment flow:

`source data -> deterministic preparation -> local reference result -> Hadoop result -> normalized comparison -> documented evidence`

## Key functions and scripts

| Area | Entry point | Responsibility |
| --- | --- | --- |
| Local checks | `scripts/run-tests.sh` | Runs every week's unit tests and syntax-checks tracked shell scripts; also run by GitHub Actions on pushes and pull requests. |
| Cluster inspection | `scripts/preflight.sh` | Read-only inspection of OS, disks, Hadoop footprint, security services, DNS, and ports before installation work. |
| Cluster provisioning | `week-02/hadoop-poc-rhel9.sh` | Guarded fresh-node Hadoop installation; not an upgrade or recovery script. |
| Cluster verification | `week-02/scripts/verify-cluster.sh` | Checks three HDFS/YARN workers, replication, readback, and a MapReduce acceptance job. |
| Apollo acquisition | `week-02/scripts/fetch_apollo11.py` | Downloads pinned transcripts and produces a manifest without committing the dataset. |
| Word count | `week-02/scripts/wordcount/mapper.py` and `reducer.py` | Tokenizes text, emits `(word, 1)`, then sums each grouped word. |
| Relational preparation | `week-03/scripts/prepare_relations.py` | Converts transcript headers and multiline speech into utterance and speaker relations. |
| SQL reference | `week-03/scripts/sqlite_baseline.py` | Loads the relations and performs the reference join and category aggregation. |
| Reduce-side join | `week-03/scripts/mapreduce/join_mapper.py` and `join_reducer.py` | Tags both relations by speaker key; the reducer buffers values because Hadoop does not guarantee value order. |
| Result verification | `week-03/scripts/verify_results.py` | Canonicalizes outputs and requires exact SQLite/Hadoop equality. |
| Shingling/minhash | `week-04/scripts/shingle.py` and `minhash.py` | Represents windows as shingle sets and estimates Jaccard similarity with signatures. |
| LSH | `week-04/scripts/lsh.py` | Uses signature banding to generate a small candidate-pair set. |
| Hadoop LSH | `week-04/scripts/hadoop/run-hadoop.sh` | Runs distributed banding and pair deduplication with immutable output paths. |
| Shared timer | `common/benchmark/run_timed.py` | Runs a command with a monotonic clock and writes versioned JSON metadata, IDs, counters, and status. |
| Map-side join | `week-05/scripts/mapreduce/map_join_aggregate.py` | Loads a tiny dimension table in each mapper, joins immediately, and fails on unknown keys. |
| Wikipedia preparation | `week-05/scripts/prepare_wikipedia.py` | Streams compressed XML into nested, complete-record TSV samples while preserving Unicode. |
| Benchmark matrix | `week-05/scripts/run-benchmark-matrix.sh` | Runs repeated SQLite/Hadoop measurements and exact comparisons at increasing sizes. |
| Runtime summary | `week-05/scripts/summarize_runs.py` | Summarizes successful JSON records, retaining first runs and reporting medians. |

## Key results

| Capability | Evidence and takeaway |
| --- | --- |
| Four-node Hadoop cluster | One controller and three workers passed HDFS, YARN, replication, readback, and MapReduce acceptance checks. |
| Distributed word count | Hadoop counted 355,040 Apollo word occurrences and 8,184 distinct words; every count matched an independent local scan. |
| SQL-equivalent operations | SQLite and Hadoop produced the same 8,420 joined utterances and four category aggregates. Mission control used fewer utterances but more words than the crew, consistent with longer instructions and explanations. |
| Similar-item search | Word 3-shingles with 25 bands of four rows recovered 93% of true cross-file pairs before exact checking. Hadoop produced 8,842 deduplicated candidates identical to the local implementation. |
| Buffer-free join | The Week 5 one-job replicated join reproduced all Apollo category totals and reduced observed Hadoop time from about 95 seconds to about 47 seconds. |
| Scaling curve | Across authentic Wikipedia samples, every SQLite/Hadoop aggregate matched. The Hadoop/SQLite median ratio narrowed from 419.7x at 2 MiB to 1.09x at 2 GiB. |
| Spark estimate | Spark would likely reduce repeated multi-stage overhead, but a cold Spark/YARN job would still have startup cost and is unlikely to beat SQLite on tiny input. |

## Where to go next

- New reader: start with the root `README.md`, then select a weekly README.
  Keep the [glossary](GLOSSARY.md) open for unfamiliar terms.
- Cluster operator: read `week-02/docs/cluster-setup.md` and the safety notes first.
- Algorithm reader: use Weeks 3-5 and their tests as executable examples.
- Results reviewer: use each weekly `Results` and `Runtime` section; generated
  data and private run logs intentionally stay outside Git.
