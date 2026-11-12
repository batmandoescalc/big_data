# Week 9: memory capacity and shared Hadoop jobs

Pictures and a short summary: [Week 9 wiki page](https://github.com/batmandoescalc/big_data/wiki/Week-9:-Memory-Capacity-and-Shared-Hadoop-Jobs).

This directory holds the memory-capacity and shared-job experiments for
[Week 9, issue #24](https://github.com/batmandoescalc/big_data/issues/24).
It measures retained-state memory on one worker and runs controlled submissions
from two real accounts. It does not modify Hadoop settings. The four-algorithm
timing comparison and the year-scale Wikipedia processing for the same issue
are separate work.

## What was measured

### Memory limits on one worker

The input is an incrementally generated sequence of unique 32-byte hexadecimal
keys, with no retained input array. We compare an exact Python set with Week 7's
FM sketch configured for 16 registers. The FM configuration is a memory control;
this experiment does not compare the accuracy of different register counts.

Every child verifies its cgroup v2 memory.max and memory.swap.max before
allocating state. A separate supervisor enforces a 120-second lifetime, a 32-task
limit, at most one CPU's time and zero swap within the service. It stops on low
host RAM or host swap use. The workload runs as the normal student identity.

| Cgroup memory cap | Exact-set last checkpoint | Failure before next checkpoint | Outcome |
| --- | ---: | ---: | --- |
| 128 MiB | 1,125,000 keys | 1,150,000 keys | cgroup OOM kill |
| 256 MiB | 2,350,000 keys | 2,375,000 keys | cgroup OOM kill |
| 512 MiB | 4,800,000 keys | 4,825,000 keys | cgroup OOM kill |

Two separate repetitions produced the same checkpoint intervals for all three
caps. These are checkpoint intervals, not claims to know the exact failing insertion.
The service's recorded memory peaks reached its configured caps. The raw
supervisor exit code was 1; systemd separately reported `Result=oom-kill` and
`ExecMainStatus=9`, which identifies the cause rather than assuming any failure
means OOM.

Under a 128 MiB cap, FM completed both 250,000 and 1,000,000 keys. Peak process
RSS was about 15.1 MiB in both runs; the logical register state was 16 bytes.
The one-million-key passes took about 28.4 and 29.9 seconds. Logical state excludes Python
objects, interpreter and shared libraries; RSS and cgroup charged memory are
different measurements and are reported separately.

Host available RAM stayed above 5,100 MiB across both studies and no swap was used. A post-run
cluster check is recorded with the Hadoop experiment results. The machine and
Hadoop services were not intentionally crashed.

The measured effective footprint was roughly 112–119 bytes per retained key,
including cgroup-accounted interpreter/table state. Applying that small-run
range to the roughly 5,726 MiB initially available gives an illustrative
exhaustion estimate of about 50–54 million keys, or about 1.6–1.7 GB of raw
32-byte key payload. Reserving 2 GiB for headroom lowers the planning budget to
about 32–34 million keys, about 1.0–1.1 GB of key payload.

**This is an extrapolation for this synthetic workload, not a measured VM crash
point or a Wikipedia file-size threshold.** Set resizing, transient old/new
tables, key sizes, duplicates, allocator behavior and other services can change
the threshold substantially. A large file streamed through a sketch can use
less RAM than a much smaller input retained in a set. There are two runs per
case; checkpoints within each run are not independent repetitions.

Sanitized measured data: [memory-summary.json](results/memory-summary.json).
The second repetition is [memory-repeat-summary.json](results/memory-repeat-summary.json).
Raw unit properties, host observations, logs and account paths remain ignored
under `runtime/`.

The initial setup exposed two integration problems: an unsupported systemd
property was rejected before execution; passing a regular logfile directly
to systemd-run's pipe forwarding caused a transient-service start failure.
The final runner uses `OOMPolicy=kill` and drains a real pipe to disk. The failed
attempt is preserved as private evidence and is not counted as a memory result.

### Hadoop baseline and same-account bursts

The fixed workload is 10,000 deterministic JSON events, 1,000 possible users,
three input files, 128 FM registers and one reducer. Every application requests
1,024 MiB for its ApplicationMaster and each map/reduce container, with a
512 MiB JVM heap, no speculative attempts and one attempt per task.

Each successful reducer result must match an independently computed local
128-register array. The canonical expected SHA-256 is
`cd2836a77fb095fb0310c51681e713f01175eb81c7b48b77abbc5ec0a4f7ace2`.
Input files use LF newlines across Windows and Linux. Their hashes are in
[input-manifest.json](results/input-manifest.json).

| Submitted jobs | Whole stage | Median client turnaround | Maximum observed RUNNING | Matching successful outputs |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 51.1 s | 51.1 s | 1 | 1/1 |
| 2 | 47.0 s | 47.0 s | 2 | 2/2 |
| 4 | 86.4 s | 59.9 s | 2 | 4/4 |

All seven applications succeeded. Every job launched three mappers and one
reducer, read 10,000 records, emitted 384 map summaries and wrote 128 final
registers. The two-job launch spread was 0.019 seconds; four jobs were submitted
within 0.056 seconds. With four submitted jobs, some waited while at most two
ApplicationMasters were observed running. This is evidence of queueing;
single runs do not establish a general performance curve or a fairness policy.

Client turnaround includes submission/startup and monitoring latency. In the
four-job stage the first observed RUNNING delays ranged about 25.5–61.1 seconds;
these are approximate ApplicationMaster wait observations, not exact first-task
queue delays. The one-job run being slower than the two-job median is not evidence
that concurrency speeds up this algorithm.

The baseline and bounded burst results are recorded in
[hadoop-summary.json](results/hadoop-summary.json). A one-account
burst measures application contention. Two actual users are measured in the
two-account rounds below. Final checks found three running workers, no active applications,
both worker Hadoop services active, and the experiment HDFS subtree HEALTHY
with zero missing/corrupt blocks or missing replicas. Global HDFS aggregate
health was also clean; per-DataNode administrative details were denied to the
normal account and were not required for this result.

### Two-account rounds

On November 11 both students ran the launcher from their own accounts with the
same agreed start time. Account A is the pull request author; account B is the
other student. Every number is in
[concurrency-results.md](docs/concurrency-results.md) and
[joint-session-summary.json](results/joint-session-summary.json).

| Jobs per account | Reached YARN | Succeeded | Cancelled | Outcome |
| ---: | ---: | ---: | ---: | --- |
| 1 | 2 | 2 | 0 | Outputs matched the expected registers. |
| 2 | 4 | 4 | 0 | Outputs matched the expected registers. |
| 4 | 8 | 8 | 0 | Outputs matched. Never more than 2 applications RUNNING at once. |
| 10 | 0 | 0 | 0 | The controller reset the SSH connections. Nothing was submitted. |
| 15 | 30 | 16 | 14 | Controller memory collapsed and both RAM guards fired. Interrupted. |

**4 each.** All 6 YARN vcores were allocated at the peak while memory
allocation peaked at 6,144 of 12,288 MiB. The last job finished about 166
seconds after the agreed start.

**10 each.** The launcher then opened one SSH connection per job. Twenty
connections at once went over the SSH server's limit on simultaneous
unauthenticated connections, and the controller reset them. This is a limit of
the sign-in path, not of Hadoop.

**15 each.** All 30 applications reached YARN. The 30 job clients ran on the
controller, and its available memory fell from about 3.4 GB to about 0.35 GB
in about 45 seconds. Swap went into use and the load average reached about 30.
Both launchers' RAM guards fired. Account A's first cancel missed application
IDs that arrived late; a second pass cancelled its 14 unfinished applications.
Account B's launcher aborted but its cleanup failed: its 15
applications were not cancelled and its 15 job clients kept running on the
controller until they were stopped by hand. Those 15 applications then ran to
completion and all 15 outputs matched the expected registers, checked by hand
afterwards. The three workers stayed healthy.

This is an interrupted experiment: 30 submitted, 16 completed, 14 cancelled.
It is not 30 successful completions and not 30 jobs running at once.

### Controller capacity: measured and estimated

The worker estimate above is about one process holding keys in memory. The
15-each round showed a different limit: the controller runs one job client
(a JVM) for every submitted job, outside YARN's memory accounting.

Measured:

- Each job client used about 209 MB on the controller (15 clients: 3,137 MB).
- The idle controller had about 5,655 MB available two minutes before the round.
- With 30 job clients, available memory fell to about 351 MB and swap was used.

Estimated from the first two measurements, not measured:

- About 27 simultaneous job clients use all the available memory (5,655 / 209).
- About 17 bring the controller down to the launcher's 2 GiB guard
  ((5,655 - 2,048) / 209).

The estimate comes from one round of one small job type. The clients did not
all start at the same instant, and other processes on the controller change
the starting point. It is not a tested threshold.

## Running the memory study

Run on one otherwise idle worker with existing sudo rights; do not run alongside
the shared job experiment. `systemd-run`, cgroup v2 and Python 3.9+ are required.
Do not run `memory_probe.py` directly without its verified cap.

```bash
python3 week-09/scripts/run_memory_study.py --output runtime/week09-memory
# After inspecting the printed plan:
python3 week-09/scripts/run_memory_study.py --output runtime/week09-memory --execute
python3 week-09/scripts/summarize_memory.py runtime/week09-memory \
  --output runtime/week09-memory-summary.json
```

The dry run creates nothing. Real runs require a new output directory, preserve
failed logs and run one capped child at a time. The runner does not reconfigure
or restart any Hadoop service. Inspect cluster health before and after it.

## Running a two-account round

Use separate SSH/Linux/HDFS identities, personal HDFS homes and personal staging.
Do not share SSH keys. The workstation transport lets you use your existing
local key without copying a private key onto the controller. Both people need
read access to the same FM source files on the controller.

Run `python3 week-09/scripts/hadoop_burst.py --help` for subcommands. For Windows,
`python` can replace `python3`. The examples below use shell placeholders:

```bash
# Existing clone on controller; configure each workstation's own values.
# List the controller first in hosts.
gateway='<NetID>@<controller>'
remote_root='/home/<NetID>/<checkout>'
ssh_key='/path/to/local/key'
rm_url='http://<controller>:8088'
hosts='<NetID>@<controller>,<NetID>@<worker1>,<NetID>@<worker2>,<NetID>@<worker3>'
input='/user/<NetID>/week-09/session/input'
output='/user/<NetID>/week-09/session/output'

python3 week-09/scripts/hadoop_burst.py prepare \
  --gateway "$gateway" --ssh-key "$ssh_key" --remote-root "$remote_root" \
  --hdfs-input "$input" --evidence runtime/joint-input

# Choose a NEW stage and an agreed UTC start at least one minute in the future.
# Both users pass the SAME start time.
python3 week-09/scripts/hadoop_burst.py launch \
  --gateway "$gateway" --ssh-key "$ssh_key" --remote-root "$remote_root" \
  --hdfs-input "$input" --hdfs-output "$output" \
  --expected runtime/joint-input/expected-registers.json \
  --evidence runtime/joint-one --stage joint-one --jobs 1 \
  --rm-url "$rm_url" --hosts "$hosts" --start-at '2026-11-11T17:05:00Z'
# This prints the plan. Add --execute to submit at the agreed start time.
```

The launcher samples the controller clock to estimate workstation offset and
records the sampling uncertainty. Starts are close in time, not guaranteed to
be exactly simultaneous. The time each batch was started is recorded. Both
users must agree on the future epoch, stage, code revision, resource requests and input hashes.

### Checks before and during a stage

The launcher refuses existing output paths or paths outside the submitting
account's HDFS home. It checks three healthy workers and polls host RAM, swap
and filesystem use through the workstation's SSH connections. It stops on RAM
below 2 GiB, any swap use, filesystem use over 85%, unhealthy/lost nodes,
unexpected job failures or a maximum 20-minute stage deadline. Monitoring adds
overhead; it is applied to every stage and is not algorithm runtime.
An SSH snapshot that times out or fails is retried once (20 seconds per attempt);
repeated connection failure still aborts. Resource-limit violations are not retried.
The terminal prints preflight, scheduled-start, application-ID and state updates.

Client budget. Before submitting, the launcher sets aside 256 MiB of
controller memory for each job client it is about to start (about 209 MB was
measured). If that would leave the controller under the 2 GiB guard, it
refuses the stage and says how many jobs would fit. The budget counts only
this launcher's clients. In a two-account round, both batches must fit
together, so agree on a job count that does.

Launch window. Health is checked every 5 seconds until every job has an
application ID, then every 15 seconds. The 15-each round lost its memory
while the clients were still starting.

Swap. The launcher refuses to start while any swap is in use. After the
15-each round the controller still had about 86 MB of swap marked used, and
82 MB two hours later. The launcher will refuse a new stage while that
remains. The guard was left as it is.

### One SSH connection per student

All job clients start from one remote shell script over a single SSH
connection. Each client's output lines and exit status come back tagged with
its job number, so per-job logs and application IDs still work. A batch of
any size is one sign-in, and every client starts together. Monitoring and
cancellation still use their own short connections, one at a time, with
`ssh -n -T` and a null stdin.

The launcher keeps that connection's stdin open for the whole stage. The
remote script watches it. When stdin closes (the launcher aborts or is
killed, or the connection drops), or the script receives a signal, it sends
SIGTERM to every job client it started and SIGKILL 10 seconds later.

### Cleanup on abort

1. Stop the job clients, as described above, so nothing new is submitted.
2. Ask the ResourceManager for applications whose name and owner both match
   this stage exactly. Repeat five times, two seconds apart, because an
   application can appear after the abort.
3. Cancel every unfinished one. A cancel that fails or times out is retried
   on the next pass and does not stop the other cancels.
4. Write the cancelled IDs to the manifest. Any ID that could not be
   cancelled is written there too and printed, to be cancelled by hand.

Another user's application is never cancelled, because every lookup uses the
exact name and owner match. Completed results are preserved.
An independent monitoring terminal remains useful if the workstation loses its
network connection. Do not rerun into the same output directories.

### What the manifest records

The manifest records client turnaround, observed ApplicationMaster wait,
final YARN states, resources, logs/counters, output checksums and health snapshots.
`startedTime` and first observed `RUNNING` are not first-task execution time.
Polling adds uncertainty, so observed waiting time must be labeled as such.
The configured poll sleep is two seconds; SSH/API calls add to the effective
interval. Scheduler snapshots distinguish queued applications from running ones.

The current queue uses FIFO application ordering and an approximately 2 GiB
ApplicationMaster memory allowance. That can restrict the number of active
applications well below the number submitted. Two accounts do not automatically
imply fair scheduling. Observe the behavior rather than changing the scheduler
to force a desired result.

## Failed attempts that changed the launcher

- `joint-one`: account A's application was submitted, but a 15-second worker
  SSH monitoring timeout triggered cancellation. A follow-up check found the
  worker healthy. The snapshot is now retried once.
- `joint-two`: a monitoring timeout happened again after the retry was added.
  One application was cancelled; the other completed first and its registers
  were verified. Neither attempt is counted as a completed round.
- Console input. The SSH processes inherited the interactive PowerShell console
  input. They now use `ssh -n -T` and a null stdin. OpenSSH's
  [manual](https://man.openbsd.org/ssh.1#n) specifies `-n` for background use.
  Console sharing was a plausible contributor to the hangs; the precise cause
  was not captured. Two same-account repetitions of two jobs each then ran
  without a monitoring timeout: all four applications succeeded and matched
  (about 39.0 and 48.1 seconds per stage). They are diagnostic runs, recorded in
  [interactive-recovery-summary.json](results/interactive-recovery-summary.json).
- 10 jobs each: one SSH connection per job hit the SSH server's limit on
  simultaneous unauthenticated connections. The controller's sshd log recorded
  `MaxStartups` throttling (effective setting `10:30:60`). A first fix opened
  the connections one at a time, which avoided the limit but serialised the
  start. The single connection replaced it. SSH server settings are unchanged.
- 15 jobs each: an aborted launcher left its job clients and applications
  running. Cleanup now works as described above.

Private evidence for the failed attempts stays in the ignored `runtime/`
directory.

## Validation and scope

Run `bash scripts/run-tests.sh`. Week 9 tests check ownership/traversal rejection,
timezone handling, cgroup-cap refusal, bounded resource requests, node/RAM
health rejection, duplicate-output registers, the client budget, and abort
cleanup: late applications are cancelled, another user's never are, and one
failed cancel does not skip the rest. The batch script is run by a real `bash`
with `sleep` commands standing in for job clients, to show that closing stdin
leaves none alive. No unit test contacts the cluster.

The one-connection launcher, the client budget and the new cleanup have not
yet been run against the cluster. The results above were measured with earlier
versions of the launcher.
