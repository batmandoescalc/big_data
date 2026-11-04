# Week 8: Streaming Sketches on Real Wikipedia Traffic

## Goal

In Week 7 we built four streaming algorithms and tested them on made-up click data. This week we gave them real data: one full day of Wikipedia traffic. Each algorithm answers one question about that day while keeping only a small summary, and we check every answer against the exact one.

## Dataset

Wikimedia publishes how many times every Wikipedia page was viewed, hour by hour, and anyone can use it (CC0). We used all 24 hours of **2026-10-27**.

- 24 files, **1.19 GB** gzipped (4.2 GB unzipped)
- **135,421,176** lines, **381,871,445** views, **49,476,423** different pages
- Each line is one page's views for one hour: `en.m Golden_Horn 9 0` means the mobile English page "Golden Horn" was viewed 9 times that hour.

It suits streaming well. The same pages come back every hour, a handful of pages get most of the views, and keeping every page exactly takes hundreds of MB. One command downloads the whole day again and records a SHA-256 for every file.

## Implementation

We read each hour straight from the gzip file, one line at a time, and hash each page once. All four sketches share that one hash, so 135 million lines stay fast enough in plain Python. For the exact answers we spill the hashes to disk in 64 pieces and total them one piece at a time, so even the "exact" side never needs all 49 million pages in memory at once.

## Results

### Bloom filter

**Question:** was a page read in the last hour (hour 23) already read earlier that day?

| Estimate | Exact | Error |
| ---: | ---: | ---: |
| 4,258,683 | 4,254,618 | 0.10% |

78% of the pages people read in the last hour had already been read earlier that day. The filter never missed a page it had seen. It wrongly said "seen" for only 0.34% of new pages, and it did that with 72 MB instead of the 386 MB an exact list would take.

### Flajolet-Martin

**Question:** how many different pages were read that day?

| Estimate | Exact | Error |
| ---: | ---: | ---: |
| 51,087,463 | 49,476,423 | 3.26% |

About 50 million different pages were read in one day. FM got within about 3% using 4,096 one-byte registers, 4 KB in total, where the exact count needed about 396 MB.

### AMS second moment

**Question:** how concentrated are the views on a few pages?

| Estimate | Exact | Error |
| ---: | ---: | ---: |
| 1.16742e13 | 1.16745e13 | 0.002% |

Attention on Wikipedia is very lopsided. The second moment says views are as concentrated as if everyone read only about 12,500 pages, out of 49 million. Part of the tiny error is luck: the plain average of all the estimates was 3.3% off, and taking the median of group averages cancels out the wild ones.

### DGIM

**Question:** of the last 1,000,000 lines, how many were "hot" (a page with 100 or more views that hour)?

| Estimate | Exact | Error |
| ---: | ---: | ---: |
| 564 | 461 | 22.3% |

Really popular pages are rare: only 461 of the last million lines were hot. DGIM counted them in a sliding window with 224 bytes instead of remembering a million bits. Because the count is small, a few extra makes the percent look big, but it stays inside DGIM's promise of at most 50% off.

## Reducing DGIM error (section 4.6.6)

![DGIM error by r](https://raw.githubusercontent.com/batmandoescalc/big_data/dev/week-08/docs/dgim-4.6.6.svg)

Basic DGIM groups the recent 1s into buckets of size 1, 2, 4, 8 and so on, and keeps one or two buckets of each size. Only the oldest bucket might hang over the edge of the window, so it gets counted as half. That one unsure bucket is why the answer can be off by up to half.

Section 4.6.6 keeps r-1 or r buckets of each size instead. With more small buckets, the unsure one is a smaller share of the total, and the worst error drops to 1/(r-1). We tested it on one real hour of Wikipedia and on random coin flips:

| r | Worst error | Average error | Memory |
| ---: | ---: | ---: | ---: |
| 2 (basic) | 48.1% | 12.9% | 320 bytes |
| 3 | 24.0% | 7.8% | 448 bytes |
| 5 | 12.5% | 4.2% | 720 bytes |
| 9 | 10.0% | 2.3% | 1,184 bytes |

Going from r=2 to r=9 cut the error about 5 times for about 4 times the memory, which is still only about 1 KB. The real data and the coin flips gave nearly the same numbers, and every answer stayed inside the book's bound.

### The bug we found in Week 7

While testing 4.6.6 we found that Week 7's DGIM counted the oldest bucket in the window in full, then added half of the next bucket, which was already outside the window. Take eight 1s in a row with a window of 5:

- Exact count: **5**
- Week 7 before the fix: **8** (60% off, worse than DGIM promises)
- The book's rule: **6** (20% off)

We fixed Week 7 to follow the book. Its own test run moved from 46 to 38 against an exact 35, from 31% error to 8.6%.

## Hadoop Streaming version

We also ran FM as a real Hadoop Streaming job on the class head node:

1. 24 mappers, one per hourly file, read all 135 million lines and each keeps its own 4,096 registers.
2. Each mapper sends only its registers, so just 98,304 lines go through the shuffle instead of 135 million.
3. The reducer keeps the largest value for each register.
4. A last step turns the merged registers into the count. Week 7's job stopped at the registers and never printed a count.

The final count matched the single-process answer exactly: 51,087,463. We can't write to HDFS yet (our account has no HDFS folder we're allowed to write to, #19), so this ran in Hadoop's local mode on the head node's own disk.

## Runtime

We ran the same code on my desktop and on the class head node. Both gave exactly the same four estimates, because the hash and the random seeds are fixed.

| | Desktop | Class head node |
| --- | --- | --- |
| Python | 3.14 | 3.9 |
| All four sketches, 135M lines | 5 min 8 s | 14 min 15 s |
| Peak memory | 305 MB (includes exact answers) | 92 MB (sketches only) |
| Hadoop FM job | - | 5 min 34 s |

On the head node everything ran at low priority with a memory cap, and we didn't change any cluster settings.

## Limitations

- One day and one random seed. FM's 3.3% is about twice its typical error, so more seeds would give a fairer range.
- The pageview files are sorted by site and title, not by time, so "the last million lines" stands in for "the most recent events".
- The head node didn't have room for the exact-answer files, so its run reused the desktop's exact answers (same files, checked by SHA-256).

## Next steps

- Noah is running the VM crash test: how many GB it takes to run the VMs out of memory, not just disk.
- A writable HDFS folder (#19) would let the Hadoop job spread across all the workers instead of running in local mode.
