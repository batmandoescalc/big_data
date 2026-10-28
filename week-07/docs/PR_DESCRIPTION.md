# Week 7: implement and evaluate streaming algorithms

## Summary

Implements the reduced Week 7 Chapter 4 streaming-algorithm study.

- Adds deterministic JSON-line click-event generation.
- Implements Bloom filter, Flajolet--Martin, AMS second-moment, and DGIM
  sketches using only the Python standard library.
- Checks every approximate result against an exact local baseline.
- Adds a bounded Hadoop Streaming Flajolet--Martin design: mapper register
  maxima merge through reducer maxima.
- Documents why this is a batch simulation, not a claim of real-time Hadoop
  streaming.
- Documents safe cluster sharing and VM-risk controls without making
  destructive changes.

## Evidence

`bash scripts/run-tests.sh` is GREEN: **78 tests** and **12 shell-script
checks** pass.

The representative 10,000-event run records:

- FM: 1,015.6 vs. 1,000 exact distinct users (1.56% error)
- AMS F2: 109,687.5 vs. 109,934 exact (0.22% error)
- DGIM: 46 vs. 35 recent error events (31.43% error; documented as a
  rare-event approximation limitation)

## Scope and limitations

- No Hadoop provisioning, configuration, HDFS data, or existing results were
  changed.
- The live Hadoop command is documented and unit-tested locally but has **not**
  been submitted to the cluster yet.
- Generated run outputs remain ignored; no private hostnames, credentials,
  keys, logs, or datasets are committed.
- The local Wiki clone is currently missing its tracked content, so this PR
  contains a reviewable `week-07/docs/wiki-page.md` rather than overwriting the
  remote Wiki.

## Review request

Please review the implementation choices, especially the bounded Hadoop FM
merge design and whether a small authorized live submission should be the next
step.
