# Week 8: streaming sketches on a real day of Wikipedia traffic

For Week 8 (#22). We ran all four streaming algorithms from Week 7 on one full day of real Wikipedia pageviews (1.19 GB gzipped, 135 million lines), both on my desktop and on the class head node. We also tried the section 4.6.6 fix for DGIM and found and fixed a bug in the Week 7 DGIM estimate. Noah is running the VM crash test separately.

## Before / After

- Before: the sketches had only seen a generated stream of up to 50,000 events.
- After: they run on 135 million real lines, and every answer sits next to the exact answer and its error.
- Before: DGIM could only be up to 50% off, and the Week 7 version could be worse because of a bug.
- After: with section 4.6.6 (r buckets per size) the worst error drops from 48% to 10% for about 1 KB of memory.
- Before: the Hadoop FM job stopped at the register array and never printed a count.
- After: a new finish step prints the estimate, and the job runs on the full day on the head node.

## Results (2026-10-27, all 24 hours)

| Question | Algorithm | Estimate | Exact | Error |
| --- | --- | ---: | ---: | ---: |
| Pages in hour 23 already read earlier that day | Bloom | 4,258,683 | 4,254,618 | 0.10% |
| Different pages read that day | FM | 51,087,463 | 49,476,423 | 3.26% |
| How concentrated views are (second moment) | AMS | 1.16742e13 | 1.16745e13 | 0.002% |
| "Hot" lines (100+ views) in the last 1,000,000 | DGIM | 564 | 461 | 22.3% |

The class head node gave the exact same four estimates as the desktop (14 min vs 5 min; 92 MB of memory for the sketches alone). The Hadoop FM job read all 135 million lines in 5 min 39 s and sent only 98,304 lines through the shuffle.

## What changed

- `week-08/`: download script, the four sketches on pageviews, the DGIM 4.6.6 study and chart, the Hadoop FM job, tests, small result files and logs, and the wiki page text.
- `week-07/scripts/streaming.py`: the DGIM estimate now halves the oldest bucket inside the range, like the book. Before, it also added half of a bucket that was already outside the window. Eight ones in a window of 5 gave 8 instead of 6 (exact 5). Week 7's own run moves from 46 (31% error) to 38 (8.6% error), exact 35. The Week 7 README and test were updated to match.

Heads up - we edited Week 7's code (see above for why). Only the DGIM estimate changed. The bucket logic is the same, so Week 7 keeps exactly the same buckets as before, and new tests cover both the old answer and the fixed one.

We can't write to HDFS yet: our account has no HDFS folder we're allowed to write to, so uploads get refused (#19). So we ran the Hadoop job in Hadoop's local mode instead, reading the files from the head node's own disk, at low priority with a memory cap. We didn't change any cluster settings.

## Checks

`bash scripts/run-tests.sh` is green on my desktop (Python 3.14): 117 tests and 13 shell-script checks. The same 117 unit tests also pass on Python 3.9 on the class head node. CI runs the checks on 3.9 and 3.12.

Requesting review from Matt. Please leave this open for his review.
