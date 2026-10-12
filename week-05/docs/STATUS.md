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
- Downloaded and checksum-verified the pinned 24.96 GiB compressed Wikipedia
  source; streamed it into nested, authentic 2 MiB, 128 MiB, 1 GiB, and 2 GiB
  samples.
- Ran three SQLite and three Hadoop attempts at every sample size. All 24
  normalized aggregate outputs matched exactly.
- Recorded the final first-run/median runtime table and Hadoop evidence.
- Passed the complete Linux-controller regression suite: 67 tests across
  Weeks 2â€“5.

## Remaining publication work

- Publish the Week 5 Wiki update and update Wiki Home.
- Reply to the relevant PR #4 review threads and add a progress comment to
  issue #6.
- Push the final documentation commit and open an unmerged Week 5 PR to `dev`
  requesting Matt's review.

The October 6 preflight passed on the approved university network with three
HDFS/YARN workers, healthy HDFS, replication two, and capacity headroom. Do not
change provisioning or cluster settings.
