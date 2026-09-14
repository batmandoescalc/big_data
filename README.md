# Big Data Hadoop Cluster Study

This repository supports a CSE 4099 independent study focused on deploying,
observing, and testing a small Hadoop cluster for large-scale data processing.
The initial work connects the distributed-file-system and MapReduce concepts in
*Mining of Massive Datasets* to a four-node RHEL 9 environment.

## Current phase

Week 2 covers Section 2.3 and a word-count exercise. The Hadoop cluster is
installed and its initial acceptance test passed. NASA's Apollo 11 transcripts
are our first real text dataset; see the [dataset notes](week-02/docs/datasets/apollo11.md).
Our Python mapper and reducer have now run successfully on those transcripts
through Hadoop Streaming. All 8,184 word totals match an independent local
counter. See the [short walkthrough and results](week-02/docs/apollo11-wordcount.md).
The [Week 2 write-up](week-02/README.md) summarizes the work and is also
published on the repository wiki. The walkthrough and MMDS
Section 2.3 reading remain the student's next steps.

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

Each week's overview is its `README.md`; supporting material lives under that
week's `docs/`, `scripts/`, and `tests/` directories as needed. Ignored `data/`
and `.local/` directories remain at the repository root for local datasets and
private access configuration.

Run this week's tests from the repository root:

```bash
python3 -m unittest discover -s week-02/tests -v
```

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
