# Week 9: Memory Capacity and Shared Hadoop Jobs

## Goal

This week asks two capacity questions. How much data can one process keep in
memory before it is killed? And what happens to a four-VM cluster when two
students submit many Hadoop jobs at the same moment?

## Memory on one worker

An exact Python set of unique keys was run under 128, 256, and 512 MiB memory
caps. It was killed at about 1.1, 2.4, and 4.8 million keys, the same in two
repetitions. Week 7's Flajolet-Martin sketch finished one million keys under
the 128 MiB cap at about 15.1 MiB of process memory, because it keeps a fixed
number of registers, not the keys.

From about 112 to 119 bytes per kept key, an exact set would use up a worker's
free memory at roughly 50 to 54 million keys. That figure is an estimate. No
VM was crashed.

## Many jobs at once

Each job reads 10,000 generated click events from three HDFS files. Three
mappers summarize user IDs into 128 FM registers and one reducer merges them.
A result counts only when its registers equal a local reference.

Two students started the same job from separate accounts at an agreed time.

| Jobs per account | Reached YARN | Succeeded | Outcome |
| ---: | ---: | ---: | --- |
| 1 | 2 | 2 | Outputs matched. |
| 2 | 4 | 4 | Outputs matched. |
| 4 | 8 | 8 | Outputs matched. At most 2 applications ran at once. |
| 10 | 0 | 0 | The SSH server reset the connections. |
| 15 | 30 | 16 | Controller memory collapsed. 14 jobs were cancelled. |

## What limited the cluster

- **Queueing.** With four jobs each, only two applications ran at a time and
  the rest waited, up to 118 seconds. All 6 vcores were allocated while half
  the memory was unused.
- **Sign-in limit.** With ten jobs each, the launcher opened one SSH
  connection per job. The SSH server limits simultaneous connections that
  have not finished signing in, and it reset them. No job was submitted.
- **Controller memory.** With fifteen jobs each, every job had a client
  process (a JVM of about 209 MB) on the controller. Thirty of them took
  available memory from about 3.4 GB to about 0.35 GB in about 45 seconds. The
  workers stayed healthy. YARN does not limit these clients.

The fifteen-each round is an interrupted experiment: 30 submitted, 16
completed, 14 cancelled. From the measurements, about 27 simultaneous job
clients would use all of the controller's available memory. That is an
estimate from one round.

## What changed in the launcher

One launcher did not cancel its jobs or stop its clients when it aborted. The
launcher now starts all clients over one SSH connection and stops them when
that connection closes, cancels applications that appear after an abort, and
refuses a stage whose clients would not fit in controller memory.

See the repository [Week 9 README](../week-09/README.md) and
[two-account results](../week-09/docs/concurrency-results.md) for commands,
data, and limitations.
