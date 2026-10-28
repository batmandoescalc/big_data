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

## Main result

On a 10,000-event, 1,000-user stream, FM estimated 1,015.6 distinct users
(1.56% error) with a 128-byte logical register array.  AMS estimated the
second moment within 0.22% using a fixed 1,024-byte logical summary.  DGIM
estimated 46 recent error events where the exact count was 35; that larger
percentage error is expected for a rare-event approximate sliding-window
question and must be reported honestly.

## Hadoop finding

Hadoop MapReduce is a batch system, not a real-time streaming system.  The
Hadoop prototype therefore distributes a bounded FM batch: mappers compute
register maxima, and a reducer takes the maximum for each register.  This
merge rule exactly reproduces the register state from a single-process run.
Bloom filters are also easy to merge with bitwise OR; AMS and DGIM need more
care at distributed batch boundaries.

## Cluster safety

Before any live job, check YARN nodes, active applications, and HDFS health;
use unique HDFS paths and small resource requests.  We will not intentionally
crash a VM.  The real risks are unbounded direct processes, exhausted disks,
and too many containers.  A bounded YARN job is the safe way to observe
resource isolation.

On October 28, the read-only health check found three running workers, no
active applications, and no missing or corrupt HDFS blocks. The student
account did not have a writable HDFS input directory, so the upload was
correctly refused and no job was submitted. The next safe step is to obtain a
student-owned HDFS project directory; we will not bypass permissions with the
Hadoop service account.

See the repository [Week 7 README](../week-07/README.md) for commands, test
coverage, limitations, and reproduction details.
