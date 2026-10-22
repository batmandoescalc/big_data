# Midsemester Checkpoint: Repository Guide

This checkpoint pauses new experiments and organizes the independent study so
a new reader can answer three questions: What was studied? Which code performs
each task? What did each experiment show?

## Getting started

1. Read the repository README for the project purpose and four-node
   architecture.
2. Open the repository's `docs/REPOSITORY_GUIDE.md` for the cross-week topic,
   function, and result index.
3. Choose a weekly README for the complete explanation and evidence.
4. Run the Week 2-5 unit tests locally; they use fixtures and do not contact
   the university cluster.

Cluster access is optional for reading and testing the repository. Never
commit credentials, SSH keys, private host details, datasets, or run logs, and
do not rerun the fresh-node provisioner on the existing cluster.

## Topics and verified results

| Week | Capability | Main result |
| --- | --- | --- |
| 1 | HDFS, YARN, MapReduce, and SSH foundations | Established the conceptual and access foundation for a controller plus three workers. |
| 2 | Hadoop word count | 355,040 Apollo word occurrences and 8,184 distinct words; exact agreement with an independent local scan. |
| 3 | Join, grouping, and aggregation | SQLite and Hadoop agreed on 8,420 joined rows and four speaker categories. |
| 4 | Minhash and LSH | Word 3-shingles and 25x4 banding recovered 93% of true cross-file near-duplicates; Hadoop/local candidates matched. |
| 5 | Join redesign and scaling | A map-side join removed the unbounded reducer buffer; at 2 GiB Hadoop's median was within about 9% of SQLite. |

## Key reusable entry points

- `scripts/preflight.sh`: read-only VM inspection.
- `week-02/scripts/wordcount/`: distributed word count.
- `week-03/scripts/`: relation preparation, SQLite reference, Hadoop join and aggregation, and exact verification.
- `week-04/scripts/`: shingling, minhash, LSH, plotting, and Hadoop banding/deduplication.
- `common/benchmark/run_timed.py`: shared JSON timing evidence.
- `week-05/scripts/`: generic map-side join, Wikipedia preparation, repeated benchmark matrix, and summaries.

## Git checkpoint

The audit recovered two useful changes that were outside `dev`: Max's
read-only preflight contribution and Matt's explanatory comments for the
shared timer. Both retain their original Git authorship. The reviewed outcome
will move from `dev` to `main` through a pull request titled **Midsemester
checkpoint**.

## Limitations and next step

This cleanup does not change experimental results or claim new performance.
After the checkpoint is reviewed, later work can resume larger-data or Spark
experiments from a repository whose structure and evidence are easier to
understand.
