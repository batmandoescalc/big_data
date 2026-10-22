# Big Data Hadoop Cluster Study

This repository supports a CSE 4099 independent study focused on deploying,
observing, and testing a small Hadoop cluster for large-scale data processing.
The initial work connects the distributed-file-system and MapReduce concepts in
*Mining of Massive Datasets* to a four-node RHEL 9 environment.

## Current phase

The midsemester checkpoint organizes the work completed in Weeks 1-5. The
cluster, algorithms, experiments, and evidence are unchanged; the focus is
making them understandable and reproducible for a new reader. Start with the
[repository guide](docs/REPOSITORY_GUIDE.md) for a cross-week index of the key
functions and results, or the [Week 6 checkpoint](week-06/README.md) for the
Git and documentation audit.

## Getting started

You do not need cluster access to read the study or run its unit tests.

1. Install Git and Python 3. No third-party Python packages are required for
   the core test suites.
2. Clone the repository and enter its directory.
3. Read the [repository guide](docs/REPOSITORY_GUIDE.md) to choose a topic.
   Unfamiliar terms are defined in the [glossary](docs/GLOSSARY.md).
4. Run every local check from the repository root:

   ```bash
   bash scripts/run-tests.sh
   ```

   This discovers each `week-*/tests` suite, syntax-checks the tracked shell
   scripts, and prints a plain-English GREEN or RED report of what each group
   of tests checks and what, if anything, failed. To run one week alone, use
   `python3 -m unittest discover -s week-04/tests -v`.

The tests use small fixtures and do not contact the university machines. The
same checks run automatically on GitHub for every push and pull request to
`dev` and `main`, under Python 3.9 (the cluster's version) and 3.12. Run
the full suite on Linux, macOS, or WSL because the installer-guard tests use
Unix account and filesystem features that native Windows Python does not have.
Cluster commands require authorized university access and an already
provisioned environment. Do not run the provisioning script on the existing
cluster. Do not commit datasets, credentials, SSH keys, internal hostnames,
authentication output, or private run logs.

For contributors, [CONTRIBUTING.md](CONTRIBUTING.md) explains the branch,
testing, review, and data-safety workflow.

## Intended architecture

| Role        | Hadoop services                         |
| ---         | ---                                     |
| Controller  | HDFS NameNode and YARN ResourceManager  |
| Worker 1    | HDFS DataNode and YARN NodeManager      |
| Worker 2    | HDFS DataNode and YARN NodeManager      |
| Worker 3    | HDFS DataNode and YARN NodeManager      |

The installer now keeps controller and worker services separate. Software is
installed on all four VMs, and the distributed storage and MapReduce acceptance
test passed.
See [the current status](week-02/docs/STATUS.md).

## Coursework by week

- [Week 1](week-01/README.md): distributed-system foundations and
  [SSH access](week-01/docs/ssh-access.md).
- [Week 2](week-02/README.md): Hadoop setup, Apollo 11 transcripts, our
  word-count program, tests, and supporting documentation.
- [Week 3](week-03/README.md): relational data preparation, natural join,
  grouping and aggregation, SQL comparison, runtime evidence, and Spark research.
- [Week 4](week-04/README.md): shingling, minhash, LSH, and finding replayed
  passages in the Apollo 11 transcripts, locally and on Hadoop.
- [Week 5](week-05/README.md): join redesign, shared timing evidence,
  Wikipedia scaling, SQLite/Hadoop comparison, and a Spark estimate.
- [Week 6](week-06/README.md): midsemester organization, branch reconciliation,
  newcomer documentation, and the `dev`-to-`main` checkpoint.

Each week's overview is its `README.md`; supporting material lives under that
week's `docs/`, `scripts/`, and `tests/` directories as needed. Ignored `data/`
and `.local/` directories remain at the repository root for local datasets and
private access configuration.

## Provisioning safety

Run `sudo bash week-02/hadoop-poc-rhel9.sh --check` to validate settings without installation.
The installer is for fresh nodes only. Before installing, establish:

- The actual controller and worker hostnames.
- Student `sudo` permissions.
- The filesystem and mount point intended for the separate data disk.
- Whether Hadoop or HDFS data already exists.
- The planned dedicated controller and three worker roles.
- The narrow firewall rules needed between the four nodes.

The installer requires a separately mounted data filesystem, rejects existing
Hadoop data and installations, and does not force NameNode formatting. It does
not disable the firewall, change SELinux, or configure SSH trust. A partially
completed installation requires inspection before continuing; rerunning this
fresh-node installer is not an upgrade or recovery procedure.

## Weekly workflow

Work should be developed on a named branch, reviewed through a pull request,
and accompanied by a concise wiki entry. Secrets, credentials, SSH keys,
authentication output, internal IP addresses, and personal identifiers must not
be committed.
