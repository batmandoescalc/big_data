# November 11: two-account Hadoop results

Two students submitted the same small Flajolet-Martin job from separate
accounts at an agreed start time. Account A is the pull request author;
account B is the other student. Data:
[joint-session-summary.json](../results/joint-session-summary.json).

| Jobs per account | Reached YARN | Succeeded | Cancelled |
| ---: | ---: | ---: | ---: |
| 1 | 2 | 2 | 0 |
| 2 | 4 | 4 | 0 |
| 4 | 8 | 8 | 0 |
| 10 | 0 | 0 | 0 |
| 15 | 30 | 16 | 14 |

## One and two jobs per account

Both rounds completed. All 2 and all 4 applications succeeded and their
outputs matched the expected 128 registers. Timings were not kept for these
two rounds. Two earlier interrupted attempts are described in the
[README](../README.md#failed-attempts-that-changed-the-launcher).

## Four jobs per account

All eight applications succeeded. Each account checked its own four outputs
against the expected registers, and all eight matched.

Snapshots showed at most two applications RUNNING and six waiting. At the peak
all 6 vcores were allocated while memory allocation was 6,144 of 12,288 MiB.
FIFO ordering and a 2,048 MiB ApplicationMaster budget were confirmed.
Allocated cores alone do not prove CPU was the only bottleneck.

Jobs reached YARN 17.6 to 19.4 seconds after the agreed start. The last one
finished 165.6 seconds after it. These are not task execution times.

| | Account A | Account B |
| --- | --- | --- |
| Reached YARN after the agreed start | 17.6 to 18.7 s | about 19 s |
| Wait before launch | 32 to 81 s (observed by the client) | 72.5, 94.0, 107.4, 118.2 s |
| Client turnaround | 46 to 108 s | not recorded here |

Account A's application IDs came first, then account B's. That fits
submission-order scheduling, not alternating users. From this round account B
estimated about 20 seconds of extra waiting per extra job. That is a
small-sample prediction and the larger rounds did not test it.

## Ten jobs per account

No job from either account reached YARN.

The launcher opened one SSH connection per job, so twenty connections arrived
at the controller together. The SSH client reported
`kex_exchange_identification: Connection reset by peer`. Account A found
`MaxStartups` throttling in the controller's sshd log at that time (effective
setting `10:30:60`). The cause is the SSH server's limit on simultaneous
unauthenticated connections. It is a limit of the sign-in path, not of Hadoop.

The launcher now starts every job client over one connection.

## Fifteen jobs per account

Each student had changed their launcher to avoid the SSH limit. All 30
applications reached YARN.

| Account | Reached YARN | Succeeded | Cancelled |
| --- | ---: | ---: | ---: |
| A | 15 | 1 | 14 |
| B | 15 | 15 | 0 |

This is an interrupted experiment: 30 submitted, 16 completed, 14 cancelled.
It is not 30 successful completions and not 30 jobs running at once. It did
not test the 20-seconds-per-job prediction.

### The controller ran out of memory

Every submitted job has a job client, a JVM that runs on the controller and
waits for the job. YARN does not count that memory.

- Each job client used about 209 MB (15 clients: 3,137 MB).
- Controller available memory fell from about 3.4 GB to about 0.35 GB in
  about 45 seconds.
- Swap went into use (260 MB at the lowest point) and the load average
  reached about 30.
- The three workers stayed healthy.

The samples, one every 5 seconds, are in
[controller-memory-fifteen-each.txt](../results/controller-memory-fifteen-each.txt).

### Both RAM guards fired

Both launchers stop a stage when a VM has under 2 GiB available. Both did.
The guard did not keep the node or the exact value that triggered it.

Account A: the first cancel missed application IDs that arrived late. A second
pass matched the exact stage names and owner and cancelled the 14 unfinished
applications. One application had already succeeded. A check after the abort
showed 107 MiB of swap in use and a one-minute load of 12.31.

Account B: the launcher aborted but its cleanup failed. None of its 15
applications was cancelled, and its 15 job clients kept running on the
controller until they were stopped by hand. The 15 applications then ran to
completion.

### Account B's fifteen jobs

| Measure | Value |
| --- | --- |
| Reached YARN after the agreed start | 52 to 58 s |
| Longest queue wait | 274 s |
| Last finish after the agreed start | about 389 s |
| Succeeded | 15 of 15 |
| Outputs matching the expected registers | 15 of 15 |

An aborted launcher skips its own output check, so these 15 outputs were
checked by hand after the run. Each was read with `hdfs dfs -cat` and compared
with the expected 128 registers using the launcher's canonical-register
comparison. All 15 matched.

Times for all 30 applications, from the ResourceManager, are in
[fifteen-each-applications.json](../results/fifteen-each-applications.json).

### Recovery

The controller was back to about 5.8 GB available within about 6 minutes.
About 86 MB of swap was still marked used then, and 82 MB two hours later.
The launcher refuses to start while any swap is in use, so it will refuse a
new stage while that remains. A final snapshot showed no active applications
and three active workers. Cluster configuration was not changed.

### What changed in the launcher

- One SSH connection starts all job clients, and closing it stops them.
- An abort stops the clients first, then looks again for late applications
  and cancels every one that matches the stage name and owner.
- A stage is refused when its job clients would not fit in the controller's
  memory.

These changes are tested locally. They have not yet been run on the cluster.
The controller estimate built from these measurements is in the
[README](../README.md#controller-capacity-measured-and-estimated).
