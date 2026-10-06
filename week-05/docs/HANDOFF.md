# Week 5 handoff

Read [STATUS.md](STATUS.md) and the [Week 5 overview](../README.md) first.

The code and local Apollo validation are complete. Do not publish a final
runtime table or claim Week 5 acceptance until the cluster becomes reachable
and the preserved JSON manifests support every number.

Next safe actions:

1. Connect through an approved university network.
2. Run `scripts/preflight-cluster.sh` read-only.
3. Repeat all tests on the Linux controller, including the Unix-specific older
   Week 2/4 cases.
4. Download the pinned 20261001 dump onto the mounted data disk, not root.
5. Prepare all nested samples and run the matrix with new HDFS paths.
6. Fill the README and Wiki runtime table from `runtime-summary.csv`.
7. Publish the Wiki, GitHub replies, issue update, and an unmerged PR to `dev`
   requesting Matt's review.

Do not run the provisioning script, format disks, alter Hadoop configuration,
overwrite prior HDFS paths, or commit generated/private data.
