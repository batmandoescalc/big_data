# Agent guide

Read this before working in the repository. It applies to any coding agent,
whichever student is driving it.

This is the record of a CSE 4099 independent study. Each `week-NN/` folder
applies one chapter of *Mining of Massive Datasets* to a four-node Hadoop
cluster. Every week follows the same loop:

`source data -> deterministic preparation -> local reference result -> Hadoop result -> exact comparison -> weekly README`

Start with [README.md](README.md), then
[docs/REPOSITORY_GUIDE.md](docs/REPOSITORY_GUIDE.md) for the cross-week index.
Use the terms in [docs/GLOSSARY.md](docs/GLOSSARY.md).

## The cluster is live: hard rules

The four university VMs are already provisioned and hold course data.

- Never run `week-02/hadoop-poc-rhel9.sh` against them. It is a fresh-node
  installer, not an upgrade or recovery tool.
- Never format a disk or the NameNode, and never change Hadoop configuration,
  firewall rules, or SELinux.
- Never overwrite or delete an existing HDFS path. Every run writes to a new
  output path.
- Touch the cluster only when the student asks for it in the current session.
  Run a small health check (workers registered, HDFS healthy) before
  submitting a job. Do not rerun a completed job just to restore context.
- The cluster is reachable only from the approved university network. An SSH
  timeout usually means the VPN is down, not that a node is broken.

## Private details stay out of Git

Never commit hostnames, IP addresses, NetIDs, keys, host-key fingerprints,
authentication output, datasets, generated databases, or private run logs.
Each student's access helpers live in the ignored `.local/` directory and
datasets in the ignored `data/` directory. Publish a sanitized example when a
log is worth keeping, as `week-04/docs/example-run-log.txt` does.

## Working in the repository

- Run `bash scripts/run-tests.sh` before pushing. It discovers every
  `week-*/tests` suite and never contacts the cluster. GitHub runs the same
  checks on every pull request.
- Code is standard-library Python that must run on Python 3.9, the cluster's
  version. Give each new test class a one-line docstring; the test report
  prints it.
- Branch from `dev` as `<name>/week-NN-topic` and open a pull request into
  `dev`. Merge it only after a teammate or the supervisor has looked at it
  and the checks pass. `main` only moves at reviewed checkpoints. See [CONTRIBUTING.md](CONTRIBUTING.md).
- A week's overview is its `README.md`; supporting material goes in that
  week's `docs/`, `scripts/`, and `tests/`. Code shared across weeks goes in
  `common/`.
- Work is tracked in GitHub issues, one per week, opened by the supervisor.
  Keep progress and open questions in the issue or the pull request. Do not
  add handoff, status, or pull-request-description files to the repository.
- The student must be able to explain what is submitted. Prefer the simplest
  design that the weekly README can explain.

## Hadoop Streaming lessons

- `-files` links each script from its own cache directory and Python resolves
  the link, so sibling modules need `-cmdenv PYTHONPATH=.`.
- With `stream.num.map.output.key.fields=2`, a reducer receives
  `key1<TAB>key2<TAB>` followed by an empty value.
- A reducer must not depend on the order of values within a key.
- Never use Python's built-in `hash()` for anything shared across processes;
  it is randomized per process.
- Scripts that call Hadoop commands over SSH need
  `source /etc/profile.d/hadoop.sh` first.
- Direct SSH to worker 2 has reset in the past for an undiagnosed reason.
  Reaching it through the controller works.

## Agent skills

### Issue tracker

Issues live in this repository's GitHub Issues, used through the `gh` CLI.
No triage labels are configured. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: one glossary at `docs/GLOSSARY.md` and decision records in
`docs/adr/`. See `docs/agents/domain.md`.
