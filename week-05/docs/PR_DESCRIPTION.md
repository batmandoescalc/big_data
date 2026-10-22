# Week 5 pull-request description

Paste the following when opening the Week 5 pull request from
`noah/week-05-scale-benchmark` into `dev`.

## Summary

Implements the Week 5 follow-up work from issue #6: a scalable join design,
shared timing evidence, a larger authentic dataset, and an evidence-based
runtime/Spark discussion.

## Results

- Replaced the new-work buffered reduce-side join with a one-job map-side
  replicated join for tiny dimension tables. Apollo reproduces all 8,420
  matched records and the existing SQLite category totals exactly.
- The optimized Apollo Hadoop job completed in 46.586 seconds, compared with
  95.341 seconds for the historical two-job pipeline. The change removes an
  unbounded reducer buffer, one YARN submission, and intermediate HDFS I/O.
- Added `common/benchmark/run_timed.py`, a shared JSON timing wrapper used by
  Weeks 3-5.
- Downloaded and checksum-verified the completed English Wikipedia article
  dump, then used authentic nested samples of 2 MiB, 128 MiB, 1 GiB, and 2 GiB.
- Ran three SQLite and three Hadoop attempts at every size; all 24 normalized
  outputs matched exactly.

| Size | SQLite median | Hadoop median |
| --- | ---: | ---: |
| 2 MiB | 0.109 s | 45.846 s |
| 128 MiB | 3.335 s | 48.885 s |
| 1 GiB | 24.368 s | 47.122 s |
| 2 GiB | 56.298 s | 61.219 s |

The observed Hadoop/SQLite median gap narrowed from 419.7x at 2 MiB to 1.09x
at 2 GiB. This is a fixed-startup-overhead result for this workload and
four-VM cluster, not a claim that either engine always wins.

## Limitation and next-scale proposal

The verified source is 24.96 GiB compressed. A several-hundred-GB benchmark is
deliberately **not** claimed: raw Wikipedia XML normalization was CPU-bound in
an interactive run, so forcing it would make an unreliable and poorly bounded
experiment. The full verified source and manifests remain available.

The proposed next step is to either parallelize/leave the Wikipedia preparation
running overnight, or first run a small ingestion pilot using Common Crawl WET
records (already-extracted web text). The pilot would measure download,
conversion, and HDFS-staging throughput before committing to hundreds of GB.
This preserves the principle of using authentic, non-duplicated data while
making the larger benchmark operationally realistic.

## Documentation and checks

- Expanded Week 3's human interpretation, runtime explanation, and
  reproducible speaker-results chart.
- Added Week 5 README, status/handoff, Wiki draft, reproducible commands,
  source provenance, timing caveats, Spark recommendation, and responsible-AI
  reflection.
- All 67 Linux-controller tests across Weeks 2-5 passed.

Progresses #6.
