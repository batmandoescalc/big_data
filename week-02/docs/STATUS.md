# Cluster setup status

Updated: 2026-09-11. Owner: Codex, working directly on branch
`setup/cluster-readiness`. No other agent owns files in this task.

For a fresh chat, start with [HANDOFF.md](HANDOFF.md). The Apollo 11 word-count
implementation is complete; resume with a brief code walkthrough as needed.

## Outcome requested

Verify access to all four VMs, prepare their assigned storage, install Hadoop,
and prove HDFS/YARN/MapReduce operation across the cluster. This sequence was
authorized. University correspondence establishes the Hadoop purpose and
assignment of separate 1 TB data disks. After reviewing the Week 2 wiki draft,
the student authorized its publication and the repository wrap-up.

## Completed and verified live

- Dedicated-key SSH and student sudo access work on all four VMs. The user
  explicitly accepted first-seen worker host keys, which are pinned in an
  ignored local file. Worker 2 uses the controller as a jump host after direct
  connection resets; the cause of those resets has not been diagnosed.
- Every VM runs RHEL 9, with four CPUs and roughly 7.5 GiB reported memory.
- All assigned 1 TB data disks passed signature, partition, mount, and LVM
  exclusion checks before initialization. They now have XFS filesystems at
  `/data`, persisted by UUID in `/etc/fstab`. Original fstab files were backed
  up. The controller's data disk letter differs from the workers'; never
  assume disk letters from the old administrator email.
- All four VMs passed the revised installer's read-only preflight.
- Java 11 and checksum-verified Hadoop 3.4.3 are installed on all four VMs.
- The controller's new HDFS namespace was initialized once. NameNode and
  ResourceManager are running and enabled at boot.
- DataNode and NodeManager are running and enabled on all three workers.
  Version, process, service, listening-port, and persistent-mount checks passed.
- A restrictive root umask initially made intermediate data directories
  inaccessible to the Hadoop account. Their ownership and modes were repaired
  without removing data. The installer now handles every ancestor explicitly,
  with a regression test. Normal SELinux file labels were applied.
- The user explicitly approved the documented firewall rules. Runtime and
  persistent configuration on every node exactly matches those peer-restricted
  rules: 12 on the controller and 15 on each worker. SELinux remains enforcing.
- Three DataNodes and three YARN NodeManagers are registered. The verifier
  stored three 12-byte input files with replication factor two, read one back
  byte-for-byte, and completed a YARN MapReduce word-count job with the exact
  expected output: `cat: 6`, `dog: 3`. HDFS fsck reported HEALTHY, with zero
  missing, corrupt, or under-replicated blocks in the test directory.
- All eight Hadoop service processes remained running after the test, with
  no additional restarts during it. No submitted, accepted, or running YARN
  applications remained, and the saved output was read back successfully.
- The first course dataset is stored in HDFS: three NASA Apollo 11 transcripts,
  totaling 2,221,376 bytes of extracted UTF-8 text. Original HTML and a source
  manifest are retained alongside the text. All seven files passed SHA-256
  readback checks; HDFS reported HEALTHY with two live replicas per block and
  zero missing, corrupt, or under-replicated blocks.

## Current state and use

The requested initial cluster setup and acceptance test are complete. HDFS
now contains both setup/test artifacts and the Apollo 11 course dataset.
The tiny acceptance-test input and output were retained at:

`/tmp/poc/verify-20260911T201122Z-W3vXBF7D`

The Week 2 word-count input is ready at:

`/datasets/apollo11/2026-09-11/text`

See [the dataset notes](datasets/apollo11.md) for sources and preparation.
The dataset-selection and custom word-count objectives are complete. Our
Python mapper and reducer ran through Hadoop Streaming in YARN job
`job_1789157262378_0002`: three launched mapper tasks, one reducer, 355,040
word occurrences, and 8,184 distinct words. Every total matched an independent
local character-scanning counter. The output is retained at
`/results/apollo11/wordcount-20260911T203041Z-81724750`.
See [the walkthrough](apollo11-wordcount.md) for word rules and run evidence.
The student explicitly selected Python with Hadoop Streaming and plans to read
the program walkthrough and textbook next. That reading remains pending.

After logging into the controller, use `sudo -u hadoop bash -l` for the current
service-account workflow, then `hdfs dfs -ls /tmp/poc` or `yarn node -list`.
See `week-02/docs/cluster-setup.md` for the prepared tools and configuration.

The tests establish basic distributed storage and job execution. They do not
establish sustained-load performance, failure recovery, or high availability.
Boot-time mount/service configuration was checked; the VMs were not rebooted.
There is one controller, so it remains a single point of failure.

Do not rerun the fresh installer against these installed nodes: its existing
installation/data guards should refuse. Ignored `.local/remote.py` provides
the verified SSH route (including worker 2's jump host); private host details,
answer files, and recovery scripts remain outside version control.

## Local validation

Eleven guard tests pass, including the restrictive-umask regression. Bash
syntax and whitespace checks pass. The generated Hadoop XML files parse, and
systemd validated all four generated service definitions. The live three-worker
storage and MapReduce acceptance test also passed. Four transcript-extraction
tests pass, covering metadata removal, text boundaries, retained transcript
details, and legacy encoding. The new dataset passed live HDFS readback and
replication checks.

Five word-count tests now pass, bringing the full suite to 20 passing tests.
The new launcher passed Bash syntax checks. Before the word-count run, three
HDFS workers and three YARN workers were online, the three input files were
present, and Python 3.9.25 was verified on the controller and all workers.
Private run logs and the independent verifier remain in `.local/`; result
files and program checksums remain under the ignored dataset results directory.

## Week 2 delivery and remaining work

The approved [Week 2 wiki page](https://github.com/batmandoescalc/big_data/wiki/Week-2:-Examples-of-MapReduce-Algorithms)
is published in wiki commit `b29e7ab`. A matching repository copy is in
[the Week 2 overview](../README.md).
The code and documentation use branch `setup/cluster-readiness`, targeting
`main` through a pull request for Matt's review and acceptance. The student
authorized pushing the branch and opening the PR, and instructed that it must
remain unmerged. Do not enable automatic merging.

Coursework is organized into `week-01/` and `week-02/`. All Week 2 code, tests,
and documents are in `week-02/`. Datasets and private access files remain
ignored at the repository root. The repository copy of the wiki write-up adds
links to the Week 2 files for navigation.

The technical assignment and wiki write-up are complete. The remaining student
work is to read [the program walkthrough](apollo11-wordcount.md) and MMDS
Section 2.3. Larger experiments are later work, not part of this week's wrap-up.
