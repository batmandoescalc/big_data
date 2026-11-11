# Week 9: Memory Capacity and Shared Hadoop Jobs

Results are ready for review; no further stress runs are planned.

[Methods and evidence](https://github.com/batmandoescalc/big_data/blob/noah/week-09-capacity-concurrency/week-09/README.md) · [Joint-run results](https://github.com/batmandoescalc/big_data/blob/noah/week-09-capacity-concurrency/week-09/docs/concurrency-results.md)

Each job reads 10,000 generated click events in three HDFS files. Three mappers summarize user IDs into 128 FM registers; one reducer merges register maxima. Successful Noah outputs matched an independent local reference. Repeated jobs measure queueing and sharing, not Wikipedia content.

- Memory: exact sets hit 128/256/512 MiB caps at about 1.1/2.4/4.8 million unique keys in two repetitions. FM completed one million keys at about 15.1 MiB process RSS. VM exhaustion figures are extrapolations.
- Eight jobs, four per account: all succeeded; at most two applications were observed RUNNING. FIFO ordering and application-manager admission affect queueing.
- Thirty submissions, fifteen per account: the RAM guard interrupted Noah's stage. Final outcomes: 16 successes and 14 cancellations. This is an interrupted experiment, not thirty successful completions.
- Closeout: zero active applications, three active workers. Inputs, results and failed attempts are preserved; cluster configuration is unchanged.

Noah's experiments are ready for review. Max separately owns the four-algorithm comparison and year of Wikipedia data. PR #25 remains draft.
