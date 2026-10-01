# Week 4 status

Updated: 2026-10-01. Branch `max/week-04-minhash-lsh`, based on `dev`.

For a fresh chat, start with [HANDOFF.md](HANDOFF.md).

## Done and verified

- Shingling, minhash, and LSH banding written in standard-library Python
  (`week-04/scripts/`), with 22 tests passing under Python 3.14 and 3.9.
- The full suite passes: 20 Week 2 tests and 22 Week 4 tests.
- Local experiment on the Apollo 11 transcripts: 14,201 windows (50 words,
  stride 25), exact Jaccard for all 7,297,737 pairs sharing a word 3-shingle,
  minhash error, LSH recall and precision for 6 settings, and the S-curve.
- Final setting word 3-shingles, b = 25, r = 4: cross-file recall 0.930 at
  Jaccard 0.5, 8,842 raw candidate pairs.
- Hadoop Streaming banding and dedupe jobs `job_1790757637442_0004` and
  `_0005` succeeded. Their 8,842 pairs are byte-for-byte identical to the
  local LSH output. Output: `/results/apollo11/week04-minhash-lsh-20261001T053647Z`.
- Health check before submission: 3 YARN nodes running; HDFS reported no
  missing, corrupt, or under-replicated blocks.
- Two earlier cluster attempts are retained at
  `/results/apollo11/week04-minhash-lsh-20261001T053135Z` (failed: import
  path) and `...-20261001T053408Z` (correct pairs, extra empty column).

## Open

- PR #5 into `dev` awaits Matt's review. Do not merge or enable auto-merge.
- The wiki page [Week 4: Finding Similar Items](https://github.com/batmandoescalc/big_data/wiki/Week-4:-Finding-Similar-Items)
  is published.
- **Student learning still to do (planned for October 2, 2026).** The student
  needs to learn this week's work at a lower level, meaning what happens under
  the hood, well enough to explain it back and walk through the work: how
  shingles become hashed sets, why a minhash row matches with probability
  equal to Jaccard, how banding produces the S-curve, how the inverted index
  gives exact ground truth, and what each Hadoop job's map, shuffle, and
  reduce steps do. Start from [the walkthrough](minhash-lsh-walkthrough.md),
  then go through the code. Do not treat this as done until the student can
  explain it.
