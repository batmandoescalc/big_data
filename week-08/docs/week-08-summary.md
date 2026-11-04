# Week 8 summary: streaming algorithms on real Wikipedia data

Issue #22, week of 2026-10-30 to 2026-11-05. Max Hawksby, with Noah Steinberg (crash test).

## What we did

- Picked a real dataset bigger than 1 GB and wrote one command that downloads it and checks every file.
- Ran all four Week 7 streaming algorithms on it and compared each answer to the exact answer.
- Tried the textbook's section 4.6.6 fix for DGIM and measured how much it cuts the error.
- Found and fixed a bug in the Week 7 DGIM estimate.
- Ran everything again on the class head node, plus FM as a real Hadoop Streaming job.
- Noah took the VM crash test (how many GB it takes to run the VMs out of memory).

## The dataset

Wikipedia hourly pageviews from Wikimedia (free to use, CC0). One full day, 2026-10-27, all 24 hours.

- 1.19 GB gzipped, 4.2 GB unzipped
- 135,421,176 lines, 381,871,445 views, 49,476,423 different pages
- Each line says how many times one page was viewed in one hour.

Why it fits: pages repeat every hour, a few pages get most of the views, and keeping every page exactly costs hundreds of MB.

## The four results

| Algorithm | Question | Estimate | Exact | Error |
| --- | --- | ---: | ---: | ---: |
| Bloom filter | Was a page read in hour 23 already read earlier that day? | 4,258,683 | 4,254,618 | 0.10% |
| Flajolet-Martin | How many different pages were read? | 51,087,463 | 49,476,423 | 3.26% |
| AMS | How concentrated are views (second moment)? | 1.16742e13 | 1.16745e13 | 0.002% |
| DGIM | How many "hot" lines (100+ views) in the last million? | 564 | 461 | 22.3% |

What they mean:

- **Bloom:** 78% of the pages read in the last hour had already been read that day. No misses, and only 0.34% false "yes" answers, using 72 MB instead of 386 MB.
- **FM:** about 50 million different pages in one day, counted with 4 KB instead of 396 MB.
- **AMS:** views are very lopsided, as if everyone read only about 12,500 pages out of 49 million.
- **DGIM:** hot pages are rare, so the count is small and the percent error looks big. It stays inside DGIM's 50% guarantee, using 224 bytes.

## DGIM finding and fix

- **Section 4.6.6:** keeping r buckets of each size instead of 2 lowers the worst error from 48% (r=2) to 10% (r=9), for about 1 KB of memory. Every query stayed inside the book's 1/(r-1) bound.
- **Bug:** Week 7's estimate added half of a bucket that was already outside the window. With eight ones in a window of 5 it said 8 instead of 6 (exact 5). We fixed it to the book's rule. Week 7's own result went from 31% error to 8.6%.

## Desktop vs. class cluster

| | Desktop | Class head node |
| --- | --- | --- |
| Python | 3.14 | 3.9 |
| Time for all four sketches | 5 min 8 s | 14 min 15 s |
| Peak memory | 305 MB | 92 MB |
| Estimates | baseline | identical |

The Hadoop FM job on the head node read all 135 million lines in 5 min 39 s. Only 98,304 lines went through the shuffle, and the final count matched the single-process answer exactly. It ran in Hadoop's local mode because students can't write to HDFS yet (#19). Nothing on the cluster was changed, and every run used low priority and a memory cap.

## Noah's crash test

Noah is running the VM crash test: how many GB of data it takes to run the VMs out of memory, not just disk.

## Open items

- A writable HDFS folder (#19) would let the Hadoop job use all the workers.
- The Week 7 DGIM fix is in this week's PR; Max is letting Noah know.
