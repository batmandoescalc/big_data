# Handoff: Apollo 11 word count completed

Updated September 11, 2026 after writing and verifying our Python MapReduce
word count. The cluster job is complete, its results are retained, and the
approved Week 2 wiki page is published.

## Start here

1. Read this file, then [STATUS.md](STATUS.md) and the
   [Apollo 11 dataset notes](datasets/apollo11.md).
2. Check `git status --short --branch`. The Week 2 delivery branch is
   `setup/cluster-readiness`, targeting `main` through a pull request. Preserve
   any later changes rather than assuming the working tree is unchanged.
3. Read [the short word-count walkthrough](apollo11-wordcount.md). Resume with
   explaining the mapper and reducer if the student requests a walkthrough.
   Do not repeat the completed run just to restore context.

Keep explanations short and simple. Explain what each meaningful step does
before executing it, without long lectures. Honor `/learn` and `/learn-more`
formats when requested. Do not use em dashes.

## Completed work and evidence

- Four university VMs run RHEL 9, Hadoop 3.4.3, and Java 11. The controller runs
  NameNode and ResourceManager; three workers run DataNode and NodeManager.
- Each assigned data disk is already formatted as XFS and mounted at `/data`,
  with persistent mount and systemd service configuration.
- The cluster acceptance test passed with three registered HDFS workers and
  three registered YARN workers. Hadoop's bundled word-count example returned
  `cat: 6`, `dog: 3` from tiny generated inputs.
- We wrote setup/verification tooling and a transcript downloader. Hadoop
  itself is installed Apache software, not a framework we wrote.
- Three NASA Apollo 11 transcripts are downloaded, extracted, and stored in
  HDFS. All seven stored files, including originals and metadata, passed
  SHA-256 readback checks. HDFS reported HEALTHY with two live replicas per
  block and zero missing, corrupt, or under-replicated blocks.

These are verified results from September 11, not a promise of current uptime.
Before submitting a new job, do a small current health check. Reinstallation
and a repeat of the whole acceptance procedure are unnecessary.

## Dataset ready to use

| Location | Purpose |
| --- | --- |
| `data/apollo11/text/` | Local UTF-8 transcripts, ignored by Git |
| `data/apollo11/raw/` | Original NASA HTML bytes |
| `data/apollo11/manifest.json` | URLs, retrieval times, encodings, sizes, SHA-256 hashes |
| `/datasets/apollo11/2026-09-11/text` | HDFS input directory for word count |
| `/datasets/apollo11/2026-09-11` | HDFS snapshot, also containing `raw/` and the manifest |

The three text files are `air-to-ground.txt`, `public-commentary.txt`, and
`onboard-voice.txt`, totaling 2,221,376 bytes, about 2.2 MB. The 439,404 whitespace
tokens include numbers, timestamps, and speaker labels; this is an input-size
statistic, not output from our own MapReduce implementation.

Text still contains case, punctuation, speaker labels, document headers, and
OCR errors. Two source pages needed Windows-1252 decoding despite declaring
UTF-8; the downloader records this. Source links and reproduction details are
in the dataset notes. Do not download or upload the same snapshot again.

## Word-count task completed

The Week 2 objectives are to review MMDS Section 2.3, get Hadoop working, find
interesting text, and code/run word count. Cluster setup and dataset selection
are complete. The student plans to read the program walkthrough and textbook;
the reading remains pending.
**Our own program has been written, run through YARN, and independently checked.**

- Python with Hadoop Streaming was explicitly selected for this exercise.
- `scripts/wordcount/mapper.py` emits `(word, 1)`; `reducer.py` adds sorted
  counts. `run-hadoop.sh` submits them with one reducer and a new output path.
- Word rules: lowercase English letters, internal apostrophes retained, curly
  apostrophes normalized, numbers and other punctuation act as separators.
  Speaker labels, headers, common words, and OCR errors remain included.
- Job `job_1789157262378_0002` succeeded with three launched mapper tasks and
  one reducer: 355,040 occurrences and 8,184 distinct words. Every output count
  matched a separate local character-scanning reference using `Counter`.
- HDFS output: `/results/apollo11/wordcount-20260911T203041Z-81724750`.
  Local counts, program hashes, and verification summary are under
  `data/apollo11/results/20260911T203041Z-81724750/` (ignored).
- Five new word-count tests and all 15 previous tests pass. Bash syntax and
  whitespace checks pass. Full run notes are in `docs/apollo11-wordcount.md`.

The next learning step is reading the walkthrough and MMDS Section 2.3.
Do not assume the student's understanding or reading is complete merely because
the code and verification are complete. Keep explanations short and simple.

The dataset is suitable for learning, not sustained-load benchmarking. Larger
stress tests and SQL-style join exercises remain later work. The approved
[Week 2 wiki page](https://github.com/batmandoescalc/big_data/wiki/Week-2:-Examples-of-MapReduce-Algorithms)
was published in wiki commit `b29e7ab`. Its repository copy is
[week-02-hadoop-and-wordcount.md](week-02-hadoop-and-wordcount.md).
Week 2 repository wrap-up was also authorized. This handoff does not authorize
publication of unrelated future work.

## Access and boundaries

- Use the existing ignored `.local/remote.py` SSH runner. It contains the
  correct account, dedicated key path, pinned host-key file, and worker 2's
  controller jump route. Do not copy these private details into tracked docs.
- Its CLI is `python3 .local/remote.py NODE SCRIPT --user hadoop`, where `NODE`
  is 0 for the controller or 1-3 for workers, and `SCRIPT` is a local shell file.
  Include `source /etc/profile.d/hadoop.sh` in scripts using Hadoop commands.
  The runner defaults to root, so explicitly select `--user hadoop` for jobs.
- For an interactive controller session, `sudo -u hadoop bash -l` enters the
  current service-account workflow. Ordinary student-shell Hadoop permissions
  have not been configured as a separate workflow.
- The user already approved accepting workers' first-seen host keys and the
  exact peer-restricted firewall rules in [cluster-setup.md](cluster-setup.md).
  Those approvals were applied and verified. Do not ask for them again.
  Host keys are pinned; unexpected key changes still require investigation.
- Worker 2's direct SSH connection resets remain undiagnosed; its existing
  jump route works. There is no need to fix that to continue this exercise.
- Do not rerun `hadoop-poc-rhel9.sh`, format disks or the NameNode, or change
  network policy to resume word count. These nodes already contain data.
- Stay within the personal Big Data project. Employer files, their aliases,
  and employer agents or material are excluded from direct and indirect
  access. The user's restriction requires specific authorization, an enterprise
  plan, and recorded boundaries in the enterprise account before any access.
- Follow the active personal account instructions. No repository-root
  `AGENTS.md` or `CLAUDE.md` existed when this handoff was prepared. Personal
  workspace paths and private access details remain outside public documents.

## Files and validation to preserve

Week 2 delivery includes `README.md`, `hadoop-poc-rhel9.sh`, `.gitignore`, the
status/setup/dataset documentation, `scripts/`, and `tests/`. Preserve these
artifacts and any subsequent changes when resuming.

- `scripts/fetch_apollo11.py`: standard-library downloader and HTML extraction.
- `scripts/verify-cluster.sh`: previously successful bundled-example test.
- `scripts/configure-cluster-firewall.sh`: previously approved rules.
- `tests/test_installer_guards.py`: 11 guard tests previously passed.
- `tests/test_apollo11_text.py`: four extraction/encoding tests passed.
- `.local/upload-apollo11.py` and `.local/apollo11-upload.log`: ignored upload
  procedure and exact verification evidence. Inspect only if needed.

Shell syntax, generated Hadoop XML, generated systemd units, and whitespace
checks previously passed as described in STATUS.md. Run checks relevant to
new changes; reuse existing evidence for unchanged setup. Local datasets,
private access files, and authentication output must remain outside Git.
