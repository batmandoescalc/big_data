# Four-node cluster setup

This procedure builds the university-authorized teaching cluster. Keep actual
hostnames, addresses, account names, keys, fingerprints, and authentication
transcripts outside version control. Use the same hostname list, software
version, ports, and data path on all four machines.

## 1. Access

Establish host trust and test the student's dedicated key on each node. Do not
use another person's administrator account. Verify the remote account,
hostname, and permitted sudo commands. A first-seen key accepted by the user
must be recorded as such, not described as independently verified.

## 2. Storage and network preparation

The administrator's correspondence assigns each VM four vCPUs, roughly 8 GB
RAM, an operating-system disk, and a separate 1 TB Hadoop data disk. Device
letters in the older correspondence differ from the controller's live layout.
Never choose the disk from its letter alone.

On every authenticated VM, inspect `lsblk`, `findmnt`, `pvs`, and read-only
`wipefs --no-act`/`blkid -p` output. Stop for existing signatures, partitions,
mounts, LVM membership, or unexpected contents. Initialize only the positively
identified project data disk after those checks and authorization are settled.
The intended layout is an XFS filesystem mounted at `/data`, with an entry by
filesystem UUID in `/etc/fstab` and Hadoop directories beneath `/data/hadoop`.
Verify the mount and its persistence before installation. Never format the OS
disk or existing HDFS storage.

Keep SELinux enforcing and the firewall enabled. Once all node addresses are
verified, use rules limited to communication among those nodes for required
HDFS/YARN services. Use an SSH tunnel for personal access to the web interfaces.
Do not open an unauthenticated teaching cluster to arbitrary clients.

### Approved firewall configuration

`week-02/scripts/configure-cluster-firewall.sh` adds the following TCP allow rules to
the existing active `public` zone, both at runtime and persistently. Each rule
is restricted to one of the other three verified VM IPv4 addresses (`/32`);
no rule permits arbitrary university or Internet clients.

| Destination role | TCP ports | Purpose |
| --- | --- | --- |
| Controller | 8020, 8030-8033, 8088, 9870 | HDFS and YARN controller services |
| Worker | 8040-8042, 9864, 9866-9867, 13562 | NodeManager, DataNode, and shuffle services |
| Worker | 32768-60999 | Dynamically bound application/task endpoints |

The dynamic range matches the live kernel ephemeral port range on all four
VMs. NodeManager's own RPC endpoint is explicitly fixed at 8041. Existing
firewall policy, SSH access, and SELinux remain in place; the script does not
reload or disable the firewall. The user explicitly approved these rules before
application. Runtime and persistent rules were independently compared against
this exact specification on all four VMs.

## 3. Install

The revised installer targets Hadoop 3.4.3 and Java 11, a dedicated controller,
and three workers. It checks the official download's SHA-512 checksum, requires
at least four CPUs and 7 GiB RAM per node, and budgets worker YARN tasks for
4 GiB RAM and two virtual cores. Validate those choices against every VM.

First run `sudo bash week-02/hadoop-poc-rhel9.sh --check` on all four prepared nodes.
Supply their actual resolvable names. This validates local prerequisites only;
it does not prove cluster connectivity or repository availability. Check the
results before installing. The installer fails on unexpected EOF rather than
silently choosing answers.

Install the controller first, initializing its fresh HDFS namespace once, then
install each worker. The controller runs NameNode and ResourceManager; workers
run DataNode and NodeManager. Foreground processes are supervised by systemd,
and service startup depends on the data mount. SSH between service accounts is
not required for this method.

This is a fresh-install procedure. Existing accounts, installation paths,
service units, or data stop it. If installation fails partway through, inspect
and resume the completed stages deliberately. Do not delete data or reinstall
blindly to bypass the checks.

## 4. Acceptance

On the controller, run `week-02/scripts/verify-cluster.sh` as the Hadoop service account
after all workers are installed. It requires:

- Three live HDFS DataNodes and three running YARN NodeManagers.
- HDFS leaving safe mode, replicated file storage, and exact file readback.
- A successful YARN MapReduce word-count job with exact expected output.
- An HDFS filesystem check of the test data.

The verifier retains a uniquely named HDFS result directory. If its job times
out, inspect the YARN application list and explicitly stop any remaining test
application before retrying. A client timeout alone may not stop a submitted job.
Also check service journals and mount-dependent startup before declaring the
cluster ready. Availability after host failure is outside this initial test;
the single controller is not highly available.

## Using the installed cluster

After SSH login to the controller, start the current Hadoop service-account
shell and inspect the cluster:

```bash
sudo -u hadoop bash -l
hdfs dfs -ls /tmp/poc
yarn node -list
```

The `/tmp/poc` path in an `hdfs dfs` command belongs to HDFS, not the VM's local
`/tmp` directory. Sample input and output from the successful acceptance run
are retained there. `exit` leaves the service-account shell.

## Local validation

```bash
bash -n week-02/hadoop-poc-rhel9.sh
bash -n week-02/scripts/verify-cluster.sh
bash -n week-02/scripts/configure-cluster-firewall.sh
python3 -m unittest discover -s week-02/tests -v
git diff --check
```

Guard tests simulate mount metadata and preserve fixture contents. They do not
replace a real four-node installation and the acceptance run.

References: [Apache releases](https://hadoop.apache.org/release/),
[Hadoop 3.4.3 cluster setup](https://hadoop.apache.org/docs/r3.4.3/hadoop-project-dist/hadoop-common/ClusterSetup.html),
and [official downloads and checksums](https://downloads.apache.org/hadoop/common/hadoop-3.4.3/).
