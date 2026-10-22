# Week 5 handoff

Read [STATUS.md](STATUS.md) and the [Week 5 overview](../README.md) first.

The code, live cluster validation, and timing matrix are complete. The
preserved records contain three SQLite and three Hadoop attempts at 2 MiB,
128 MiB, 1 GiB, and 2 GiB; every normalized aggregate matched exactly.

Remaining safe actions:

1. Publish the prepared Week 5 Wiki update and update Wiki Home.
2. Reply to Matt's Week 3 review threads and add a progress comment to issue #6.
3. Push the final documentation commit and open an unmerged PR to `dev`
   requesting Matt's review.
4. Treat a larger Wikipedia run as a future, parallel or overnight experiment;
   do not rerun provisioning, format disks, alter Hadoop configuration, or
   overwrite existing HDFS paths.

Do not run the provisioning script, format disks, alter Hadoop configuration,
overwrite prior HDFS paths, or commit generated/private data.
