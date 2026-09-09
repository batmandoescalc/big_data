# Big Data Hadoop Cluster Study

This repository supports a CSE 4099 independent study focused on deploying,
observing, and testing a small Hadoop cluster for large-scale data processing.
The initial work connects the distributed-file-system and MapReduce concepts in
*Mining of Massive Datasets* to a four-node RHEL 9 environment.

## Current phase

Week 1 is limited to foundations and environment access:

- Review Sections 2.1 and 2.2 of *Mining of Massive Datasets*.
- Verify SSH access to the controller and three worker virtual machines.
- Understand the supplied proof-of-concept provisioning script.
- Document repeatable setup and safety checks before changing the servers.

Algorithm implementations beginning in Section 2.3 are outside the current
phase.

## Intended architecture

| Role        | Hadoop services                         |
| ---         | ---                                     |
| Controller  | HDFS NameNode and YARN ResourceManager  |
| Worker 1    | HDFS DataNode and YARN NodeManager      |
| Worker 2    | HDFS DataNode and YARN NodeManager      |
| Worker 3    | HDFS DataNode and YARN NodeManager      |

The final roles must be confirmed against the actual server configuration before
provisioning. The supplied script currently enables worker services on every
node, including the controller.

## Repository contents

- `hadoop-poc-rhel9.sh`: interactive proof-of-concept Hadoop installer.
- `docs/ssh-access.md`: safe, generic SSH-access procedure.
- `docs/week-01-foundations.md`: notes on distributed file systems and
  MapReduce.

## Provisioning safety

Do not run `hadoop-poc-rhel9.sh` until the team has confirmed:

- The actual controller and worker hostnames.
- Student `sudo` permissions.
- The filesystem and mount point intended for the separate data disk.
- Whether Hadoop or HDFS data already exists.
- Whether the controller should also run worker services.
- Which firewall and SELinux changes, if any, are authorized.

Formatting a NameNode can destroy existing HDFS metadata. Disabling a firewall
or weakening SELinux should not be treated as a routine setup step.

## Weekly workflow

Work should be developed on a named branch, reviewed through a pull request,
and accompanied by a concise wiki entry. Secrets, credentials, SSH keys,
authentication output, internal IP addresses, and personal identifiers must not
be committed.
