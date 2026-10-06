# Week 5 status

Updated October 6, 2026.

## Complete

- Reconciled merged Week 3 `main` and merged Week 4 `dev` histories.
- Added one shared, versioned JSON command timer to Weeks 3–5.
- Replaced the new-work buffered reduce-side join with a generic map-side
  replicated join and one aggregation job.
- Reproduced all four Apollo totals exactly with 8,420 matched records.
- Ran the optimized join on YARN: 46.585714 seconds, exact SQLite match, two
  mappers, one reducer, and seven combined records entering the reducer.
- Added strict unknown-key behavior and explicit reporting for Apollo's 10
  unmatched records.
- Added verified Wikimedia source selection, streaming XML/bzip2 preparation,
  nested complete-record samples, SQLite/Hadoop runners, cluster preflight,
  exact comparison, and first/median summarization.
- Expanded the Week 3 human interpretation and runtime explanation.
- Week 3 and Week 5 local test suites pass.

## In progress

- Download/prepare the pinned 25.05 GiB compressed Wikipedia dump.
- Run three SQLite/Hadoop attempts at 2 MiB, 128 MiB, 1 GiB, and 10 GiB.
- Run both engines through the revised 2 GiB cap and record all three attempts.
- Populate the final runtime/counter/crossover table.
- Publish the Wiki update, GitHub review replies, issue progress comment, and
  final unmerged PR after evidence is present.

The October 6 preflight passed on the approved university network with three
HDFS/YARN workers, healthy HDFS, replication two, and capacity headroom. Do not
change provisioning or cluster settings.
