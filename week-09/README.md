# Week 9: memory capacity and shared Hadoop jobs

**November 11 closeout:** see [joint results and remaining work](docs/concurrency-results.md). Eight jobs succeeded across both accounts; the thirty-submission attempt ended with 16 successes and 14 cancellations after the RAM guard. No further stress runs are planned.


This is Noah's part of [Week 9, issue #24](https://github.com/batmandoescalc/big_data/issues/24).
Max owns the four-algorithm timing comparison, his HDFS setup and year-scale
Wikipedia processing. This directory measures retained-state memory and prepares
controlled submissions from two real accounts. It does not modify Hadoop settings.

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
1,024 MiB for its application manager and each map/reduce container, with a
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
application managers were observed running. This is evidence of queueing;
single runs do not establish a general performance curve or a fairness policy.

Client turnaround includes submission/startup and monitoring latency. In the
four-job stage the first observed RUNNING delays ranged about 25.5–61.1 seconds;
these are approximate application-manager wait observations, not exact first-task
queue delays. The one-job run being slower than the two-job median is not evidence
that concurrency speeds up this algorithm.

The baseline and bounded burst results are recorded in
[hadoop-summary.json](results/hadoop-summary.json). A one-account
burst measures application contention; only the joint session can measure two
actual users. Large bursts are extensions, not prerequisites for validating the
launcher. Final checks found three running workers, no active applications,
both worker Hadoop services active, and the experiment HDFS subtree HEALTHY
with zero missing/corrupt blocks or missing replicas. Global HDFS aggregate
health was also clean; per-DataNode administrative details were denied to the
normal account and were not required for this result.

At roughly two running applications per wave, thirty such jobs might take
10–15 minutes once accepted, plus preparation and verification. This is only
a scheduling estimate from small bursts. The joint session can attempt the
larger stages if both accounts are ready early and smaller stages remain healthy;
no 8-, 16- or 30-job result is claimed here.

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

## Wednesday two-user session: November 11, 11:45–12:45 Eastern

Prepare code and inputs before the hour. Keep the first 20 minutes for access
checks and a one-job baseline per account, 25 minutes for synchronized bursts,
and the last 15 minutes for output/health checks. Stop new submissions at 12:30.
Minimum evidence is one verified job from each account and one scheduled job
each. Increase to two each, then four each only if time and health allow.

Use separate SSH/Linux/HDFS identities, personal HDFS homes and personal staging.
Do not share SSH keys. The workstation transport lets you use your existing
local key without copying a private key onto the controller. Both people need
read access to the same FM source files on the controller.

Run `python3 week-09/scripts/hadoop_burst.py --help` for subcommands. For Windows,
`python` can replace `python3`. The examples below use shell placeholders:

```bash
# Existing clone on controller; configure each workstation's own values.
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
# Both users pass the SAME start time. 12:05 Eastern = 17:05 UTC on November 11.
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
be exactly simultaneous; actual submissions are timestamped. Both users must
agree on the future epoch, stage, code revision, resource requests and input hashes.

The launcher refuses existing output paths or paths outside the submitting
account's HDFS home. It checks three healthy workers and polls host RAM, swap
and filesystem use through the workstation's SSH connections. It stops on RAM
below 2 GiB, any swap use, filesystem use over 85%, unhealthy/lost nodes,
unexpected job failures or a maximum 20-minute stage deadline. Monitoring adds
overhead; it is applied to every stage and is not algorithm runtime.
An SSH snapshot that times out or fails is retried once (20 seconds per attempt);
repeated connection failure still aborts. Resource-limit violations are not retried.
The terminal prints preflight, scheduled-start, application-ID and state updates.

The November 11 `joint-one` attempt submitted Noah's application successfully
but a 15-second worker SSH monitoring timeout triggered cancellation. A follow-up
check found the worker healthy. That failed attempt is preserved in private
evidence and is not included among the seven successful November 10 jobs.
Use a new stage/output path and future time for the retry; do not overwrite it.

The `joint-two` attempt also hit a monitoring timeout after the retry was added.
One application was canceled; the other completed before cancellation and its
registers were independently verified. This interrupted stage is not a completed
two-user benchmark. Both attempts remain in the private evidence directories.

The SSH processes originally inherited the interactive PowerShell console input.
They now use `ssh -n -T` and a null stdin for submissions, monitoring and
cancellation. OpenSSH's [manual](https://man.openbsd.org/ssh.1#n) specifies `-n`
for background use. Console sharing was a plausible contributor to the hangs;
the earlier timeout's precise internal cause was not captured. Increasing a
timeout alone did not resolve the problem. Diagnostic results after console
isolation are recorded separately in
[interactive-recovery-summary.json](results/interactive-recovery-summary.json).
Two interactive PowerShell repetitions submitted two jobs each. All four
applications succeeded, their 128 registers matched the independent baseline,
and neither run had a monitoring timeout or retry. The stages took about
39.0 and 48.1 seconds including client/monitoring overhead. These are diagnostic
same-account runs, not replacement data for the interrupted two-user attempts.
The complete local suite now passes 93 tests and 12 shell syntax checks.

The larger `joint-twenty-338` attempt exposed a separate SSH login-burst limit.
Controller sshd logs explicitly recorded `MaxStartups` throttling at that time
(effective configuration `10:30:60`). No application IDs were captured in this
aborted stage. It is not counted as a successful twenty-job experiment.

The launcher now waits for an authenticated remote-shell acknowledgement before
opening the next job SSH connection. It does not wait for each Hadoop job to
finish, so applications can still overlap. Actual submission/authentication times
are recorded; a shared scheduled start does not mean all submissions occur in
the same instant. SSH server settings are unchanged. A read-only test successfully
held ten authenticated connections while querying YARN metrics; that test
submitted zero Hadoop jobs and is not a ten-job YARN result.

On abort, it cancels only application IDs found in its own clients or by an
exact job-name and submitting-user match. Completed results are preserved.
An independent monitoring terminal remains useful if the workstation loses its
network connection. Do not rerun into the same output directories.

The manifest records client turnaround, observed application-manager wait,
final YARN states, resources, logs/counters, output checksums and health snapshots.
`startedTime` and first observed `RUNNING` are not first-task execution time.
Polling adds uncertainty, so observed waiting time must be labeled as such.
The configured poll sleep is two seconds; SSH/API calls add to the effective
interval. Scheduler snapshots distinguish queued applications from running ones.

The current queue uses FIFO application ordering and an approximately 2 GiB
application-manager memory allowance. That can restrict the number of active
applications well below the number submitted. Two accounts do not automatically
imply fair scheduling. Observe the behavior rather than changing the scheduler
to force a desired result.

## Validation and scope

Run `bash scripts/run-tests.sh`. Week 9 tests check ownership/traversal rejection,
timezone handling, cgroup-cap refusal, bounded resource requests, node/RAM
health rejection, duplicate-output registers and cancellation of only a recorded
experiment application. No unit test contacts the cluster.

This branch starts from dev and adds Week 9 only. It does not incorporate Max's
unmerged Week 8 DGIM changes or Noah's separate Week 7 documentation correction;
the FM code used here is unchanged by either. Keep both earlier branches intact.

