# Big Data Hadoop Cluster Study

This repository supports a CSE 4099 independent study focused on deploying,
observing, and testing a small Hadoop cluster for large-scale data processing.
The initial work connects the distributed-file-system and MapReduce concepts in
*Mining of Massive Datasets* to a four-node RHEL 9 environment.

## Current phase

The Hadoop cluster is installed and its initial acceptance test passed. Week 2
loaded NASA's Apollo 11 transcripts and ran a verified Python word-count job.
Week 3 converts the air-to-ground transcript into relations and performs a
natural join followed by grouping and aggregation in both SQLite and Hadoop.
All 8,420 joined rows and all four aggregate rows match exactly. See the
[Week 3 write-up and results](week-03/README.md).

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

Each week's overview is its `README.md`; supporting material lives under that
week's `docs/`, `scripts/`, and `tests/` directories as needed. Ignored `data/`
and `.local/` directories remain at the repository root for local datasets and
private access configuration.

Run this week's tests from the repository root:

```bash
python3 -m unittest discover -s week-03/tests -v
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
