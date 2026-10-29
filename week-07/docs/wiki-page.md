# Week 7: Mining Data Streams

## What we studied

Chapter 4 asks how to answer useful questions when data arrives continuously
and cannot all be kept in memory.  Instead of retaining every event, a
streaming algorithm keeps a compact summary and accepts a controlled amount of
approximation.

## Implemented locally

- **Bloom filter:** membership checks with no false negatives and possible
  false positives.
- **Flajolet--Martin:** approximate distinct-user count using hash registers.
- **AMS:** approximate second frequency moment, which reveals whether traffic
  is evenly spread or concentrated among a few users.
- **DGIM:** approximate count of recent error events using exponentially sized
  buckets.

All four operate one event at a time.  Each is tested against an exact answer
on a deterministic JSON-line click stream.

An additional eight-event example lists every user/status record and checks
all four outputs by hand: four distinct users, second moment 22, and four error
bits. FM estimates 4.298, AMS estimates 22.75, and DGIM returns 4.

## Main result

On a 10,000-event, 1,000-user stream, FM estimated 1,015.6 distinct users
(1.56% error) with a 128-byte logical register array.  AMS estimated the
second moment within 0.22% using a fixed 1,024-byte logical summary.  DGIM
estimated 46 recent error events where the exact count was 35; that larger
percentage error is expected for a rare-event approximate sliding-window
question and must be reported honestly.

## Repeated size check

Three deterministic seeds were run at 10,000, 25,000, and 50,000 events.
With a deliberately small 32-register FM sketch and 32 AMS estimators, the
exact distinct-user set grew from about 84 KiB to 780 KiB while FM remained at
32 bytes and AMS at 512 bytes. Median FM error ranged from 2.45% to 11.47%; it
is the visible trade-off for retaining a tiny, fixed summary. The accompanying
chart is in `week-07/docs/memory-growth.svg`.

## Hadoop finding

Hadoop MapReduce is a batch system, not a real-time streaming system. The
Hadoop prototype therefore distributes a bounded FM batch: mappers hash users,
count trailing zeros, and emit partition-local register maxima; the reducer
only takes the maximum for each register across mappers. This
merge rule exactly reproduces the register state from a single-process run.
Bloom filters are also easy to merge with bitwise OR; AMS and DGIM need more
care at distributed batch boundaries.

FM was selected because its fixed register arrays merge exactly with an
associative `max`, producing a useful numeric distinct-count estimate with
very little shuffle data. AMS needs coordinated global sampling, and DGIM
needs event ordering/window boundaries that ordinary MapReduce partitions do
not preserve.

## Cluster safety

Before any live job, check YARN nodes, active applications, and HDFS health;
use unique HDFS paths and small resource requests.  We will not intentionally
crash a VM.  The real risks are unbounded direct processes, exhausted disks,
and too many containers.  A bounded YARN job is the safe way to observe
resource isolation.

Concretely, a VM can become unavailable if an unbounded process exhausts its
8 GB of RAM and triggers Linux's out-of-memory killer, if logs/temporary files
fill the root filesystem, if HDFS fills worker data disks, or if too many
processes/file descriptors prevent Hadoop daemons from operating. CPU
saturation usually causes slowness/timeouts rather than a crash. Loss of the
controller's NameNode or ResourceManager has cluster-wide impact. YARN limits
help inside containers but do not protect against direct processes or full
filesystems, so the safe experiment monitors memory, disk, containers, and
daemon health around a bounded job rather than intentionally crashing a VM.

On October 28, the read-only health check found three running workers, no
active applications, and no missing or corrupt HDFS blocks. The student
account did not have a writable HDFS input directory, so the upload was
correctly refused and no job was submitted. The next safe step is to obtain a
student-owned HDFS project directory from the cluster/HDFS administrator. Matt
did not create or control this permission model, so the administrator must be
identified or contacted; we will not bypass permissions with the Hadoop
service account.

See the repository [Week 7 README](../week-07/README.md) for commands, test
coverage, limitations, and reproduction details.
