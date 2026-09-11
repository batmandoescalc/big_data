# Big Data Hadoop Cluster Study

This repository supports a CSE 4099 independent study focused on deploying,
observing, and testing a small Hadoop cluster for large-scale data processing.
The initial work connects the distributed-file-system and MapReduce concepts in
*Mining of Massive Datasets* to a four-node RHEL 9 environment.

## Current phase

The Week 1 foundations phase covered reading and environment access:

- Review Sections 2.1 and 2.2 of *Mining of Massive Datasets*.
- Verify SSH access to the controller and three worker virtual machines.
- Understand the supplied proof-of-concept provisioning script.
- Document repeatable setup and safety checks before changing the servers.

Week 2 covers Section 2.3 and a word-count exercise. The Hadoop cluster is
installed and its initial acceptance test passed. NASA's Apollo 11 transcripts
are our first real text dataset; see the [dataset notes](docs/datasets/apollo11.md).
Our Python mapper and reducer have now run successfully on those transcripts
through Hadoop Streaming. All 8,184 word totals match an independent local
counter. See the [short walkthrough and results](docs/apollo11-wordcount.md).
The [Week 2 write-up](docs/week-02-hadoop-and-wordcount.md) summarizes the work
and is also published on the repository wiki. The walkthrough and MMDS
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
See `docs/STATUS.md`.

## Repository contents

- `hadoop-poc-rhel9.sh`: interactive proof-of-concept Hadoop installer.
- `docs/ssh-access.md`: safe, generic SSH-access procedure.
- `docs/week-01-foundations.md`: notes on distributed file systems and
  MapReduce.
- `docs/cluster-setup.md`: preparation, installation, and acceptance procedure.
- `scripts/verify-cluster.sh`: checks all workers and runs a MapReduce word count.
- `scripts/fetch_apollo11.py`: downloads three NASA transcripts and extracts text.
- `docs/datasets/apollo11.md`: dataset sources, preparation, and HDFS input location.
- `scripts/wordcount/`: our Python mapper, reducer, and Hadoop job launcher.
- `docs/apollo11-wordcount.md`: word rules, worked example, and verified results.

## Provisioning safety

Run `hadoop-poc-rhel9.sh --check` to validate settings without installation.
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
