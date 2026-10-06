# Week 5: Scaling, Join Design, and Runtime Investigation

## Goal

This week asks why SQLite finished the small Apollo query almost instantly
while the original two-job Hadoop version took about 95 seconds, and how that
comparison changes as the data grows from megabytes toward 100 GiB.

## Join redesign

The corrected Week 3 reduce-side join **did work**: it produced all 8,420
expected joined rows and matched SQLite exactly. Its reducer needed to buffer
fact rows because Hadoop groups by key but does not guarantee value order.
That can become a memory problem for a very popular key.

Week 5 instead copies the tiny lookup table to every mapper. Each mapper joins
a fact immediately, then a combiner/reducer aggregates count, words, and text
bytes in one job. The Apollo validation reproduced the original four category
totals exactly without an unbounded reducer buffer or intermediate HDFS job.

This map-side method is appropriate only when one relation is genuinely small.
A large-to-large join still needs a partitioned reduce-side design.

## Data and experiment

The source is the 2026-10-01 English Wikipedia
`pages-articles-multistream` split dump, completed October 2. Its 71 files total
25.05 GiB compressed. Source URLs and checksums come from the pinned
`dumpstatus.json` file.

The parser streams bzip2/XML and creates:

- `pages.tsv`: page ID, namespace ID, words, text bytes, and text;
- `namespaces.tsv`: namespace ID and name.

Samples target 2 MiB, 128 MiB, 1 GiB, 10 GiB, and 100 GiB. They contain only
authentic complete records and are nested rather than duplicated.

SQLite and Hadoop run the same join/group/aggregate query three times per
size. We retain the first time, report the median, keep preparation separate,
and require exact output equality. A shared JSON timer also captures YARN IDs
and Hadoop counters.

## Current results

Apollo local validation matched exactly:

| Category | Records | Words |
| --- | ---: | ---: |
| crew | 4,490 | 53,303 |
| mission-control | 3,884 | 61,246 |
| recovery | 11 | 66 |
| remote-site | 35 | 233 |

The Wikipedia timing matrix is pending because the cluster is unreachable
from the current network. No placeholder timing values are being presented as
measurements.

## Why small Hadoop was slow

The Week 3 input was only about 2.2 MB. Hadoop paid for two YARN submissions,
container/JVM/Python startup, two shuffle/sort phases, an intermediate HDFS
write/read, and reducers, but had too little data to spread useful work across
three workers. SQLite stayed in one process. The scaling curve will show when
larger parallel work begins to offset Hadoop's fixed startup cost.

## Would Spark help?

Probably for a multi-stage distributed pipeline, because Spark can reuse
executors, broadcast the tiny lookup table, and avoid intermediate HDFS I/O.
However, cold Spark-on-YARN still has startup overhead and probably will not
beat SQLite at 2 MiB. Spark is not installed this week. A later measured trial
should use Spark 3.5.7 on the existing YARN/Java 11 cluster.

## Safety and reproducibility

The runner requires three HDFS workers, three YARN workers, healthy HDFS,
replication two, and disk headroom. It uses new immutable HDFS paths and does
not provision, reformat, or reconfigure the cluster. Dumps, generated data,
databases, logs, and private access details are excluded from Git.
