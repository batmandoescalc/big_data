# Week 8: Streaming Sketches on Real Wikipedia Traffic

## Goal

Week 7 built four stream summaries (Bloom, Flajolet-Martin, AMS, DGIM) and
tested them on a generated stream.  This week runs the same four ideas on a
real, public stream of more than 1 GB: one full day of Wikipedia pageview
counts.  Every approximate answer sits beside the exact answer and its error.

## Dataset

| Item | Value |
| --- | --- |
| Source | Wikimedia Analytics hourly pageview dumps, <https://dumps.wikimedia.org/other/pageviews/> |
| License | CC0 1.0 public domain dedication ("All Analytics datasets are available under the Creative Commons CC0 dedication", stated on the [pageviews readme](https://dumps.wikimedia.org/other/pageviews/readme.html) and the [dumps legal page](https://dumps.wikimedia.org/legal.html), checked 2026-11-03) |
| Slice | 2026-10-27, hours 00-23 (UTC): 24 files `pageviews-20261027-HH0000.gz` |
| Size | 1,194,014,319 bytes gzipped (1.19 GB); 4,224,610,235 bytes (4.2 GB) uncompressed |
| Lines | 135,421,176 lines, 381,871,445 views, 0 malformed lines (the parser counts and skips any it finds) |
| Checksums | `manifest.json` next to the data lists url, bytes, and SHA-256 per file |

Each line is one page's view count for one hour:

```text
wiki_code page_title views 0
en.m Golden_Horn 9 0
```

`wiki_code` names the site (`en` = English Wikipedia desktop, `en.m` =
mobile), `page_title` uses underscores instead of spaces, and the last field is
always `0` (a retired response-size column).  A page appears at most once per
hour file, and lines are sorted by wiki and title, not by time.  The stream key
is `wiki_code + " " + page_title`; a line with `views = c` stands for c views.

### Why this data fits each algorithm

| Algorithm | Question on this data | Why it fits |
| --- | --- | --- |
| Bloom filter | Was a page read in hour 23 already read earlier that day? | About 48 million distinct keys arrive in hours 00-22; storing them all costs far more than a bit array. |
| Flajolet-Martin | How many different pages were read that day? | The same pages repeat every hour, so lines (135 million) far exceed distinct pages (49 million). |
| AMS | How concentrated are views on a few pages (second moment, the "surprise number")? | Views are very skewed: a few pages (Main Page, breaking news) get tens of thousands of views an hour, most get one. |
| DGIM | Among the last 1,000,000 lines, how many were "hot" (100+ views in that hour)? | Hot lines are rare (0.18% of lines in hour 00), giving a sparse 0/1 stream with a natural sliding window. |

### Download

```bash
python3 week-08/scripts/download_pageviews.py --dry-run          # HEAD only: URLs and total bytes
python3 week-08/scripts/download_pageviews.py --out-dir data/week-08/pageviews
```

Downloads are sequential (one file at a time), send the User-Agent
`big_data-coursework/1.0`, skip any file whose size already equals the
server's Content-Length, and resume a partial file with an HTTP Range request.
`data/` is ignored by Git; never commit the dumps.

## How the sketches run on this stream

`scripts/pageviews.py` reads each hour straight from gzip, one line at a time,
and hashes each key exactly once (64-bit BLAKE2b).  Each sketch takes what it
needs from that single hash, because 24 separate hashes per line (as the Week
7 classes do) would make 135 million lines far too slow in pure Python.

- **Bloom**: hours 00-22 insert, hour 23 only asks.  The k bit positions come
  from double hashing, `a + i*b` (a = low 32 bits, b = high 32 bits).  Sized
  for 60 million keys at a 1% target: 575,103,503 bits (71.9 MB), k = 7.
- **FM**: the low 12 bits pick one of 4,096 registers and the trailing zeros
  of the other 52 bits are the book's R ("stochastic averaging").  Registers
  combine with a harmonic mean and the HyperLogLog bias constant, the standard
  refinement when each key updates one register instead of all of them.
- **AMS**: the book's estimator on the *expanded* stream, where a line with c
  views is c arrivals, without expanding it.  Each of 4,096 variables keeps
  the arrival number of its next reservoir replacement (after a replacement at
  T, the next is at floor(T/U)+1).  A line covering arrivals n+1..n+c replaces
  every variable whose next arrival falls inside it, starting its count at the
  arrivals left in that line; later lines of the same page add their full c.
  The answer is the median of 8 group means (512 variables each).  We first
  tried 64 groups of 64; on a two-hour trial (hours 22-23) that was 36% low,
  because heavy pages are sampled so rarely that most small groups miss them
  and the median falls below the true mean.  Larger groups fixed it (0.9% on
  the same trial); this was chosen before the full-day run below.
- **DGIM**: bit = 1 when a line has 100+ views.  It reuses the Week 7 bucket
  code, but jumps over runs of zeros in one step and uses the book's estimate
  (see the finding below).  Window N = 1,000,000 lines over all 24 hours.

The exact answers need every distinct key, 49 million, which would
need several GB in a Python dict.  Instead the run writes (hash, views) pairs
to 64 partition files by the top 6 hash bits (16 bytes per line, about 2.2 GB of temporary disk)
and totals one partition at a time.  Keys are compared by their 64-bit hash;
with about 5e7 keys the chance of any collision is about n^2/2^65, roughly
1e-4.  Exact DGIM keeps the arrival times of the one-bits inside the window.

`tests/test_pageviews.py` proves the fast versions match Week 7 or exact math:
the zero-skipping DGIM keeps exactly Week 7's buckets; weighted AMS picks the
same position and count as a brute-force replay on the expanded stream; the
inline loops give the same answers as the sketch classes; and a hand-made
three-hour dump gives hand-computed exact answers.

### Run

```bash
flock /tmp/crew-heavy.lock python3 week-08/scripts/run_pageviews.py \
  --input-dir data/week-08/pageviews --hours 00-23 \
  --output data/week-08/results/full-day.json --work-dir data/week-08/tmp
python3 week-08/scripts/run_pageviews.py --input-dir data/week-08/pageviews \
  --hours 12 --output runtime/week-08/hour-12.json     # quick one-hour check
```

## Results: full day 2026-10-27

Run on a 16-core WSL2 workstation (Linux 6.6, Python 3.14.4), one process,
pure Python, `flock`-guarded: 314 s for one streaming pass with all four
sketches, plus 15 s for the exact answers; 330 s wall clock, peak resident
memory 314 MB.  Full output: `data/week-08/results/full-day.json` (not
committed).

| Algorithm | Question | Estimate | Exact | Error | Sketch memory | Exact memory (logical) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Bloom | Hour-23 pages already seen earlier that day | 4,258,683 | 4,254,618 | 0.10% | 71.9 MB | 386 MB |
| FM | Distinct pages in the day | 51,087,463 | 49,476,423 | 3.26% | 4 KB | 396 MB |
| AMS | Second moment F2 of views per page | 1.16742e13 | 1.16745e13 | 0.002% | 64 KB | 792 MB |
| DGIM | Hot lines among the last 1,000,000 | 564 | 461 | 22.3% | 224 B | 125 KB |

What the numbers say:

- **Bloom**: 78% of the 5,453,115 pages read in hour 23 had been read earlier
  that day.  There were 0 false negatives.  Among the 1,198,497 truly new
  pages, 4,065 were wrongly called "seen": a 0.34% false-positive rate, which
  matches the formula's 0.34% for 48,277,926 inserted keys.  It is below the
  1% target because the filter was sized for 60 million keys.
- **FM**: about 51 million different pages from 4,096 one-byte registers.  The
  expected error for 4,096 registers is about 1.6%, so 3.3% is a roughly
  two-standard-error miss on this one seed.
- **AMS**: the "surprise number" F2 = 1.17e13.  If the 381.9 million views
  were spread evenly over 49.5 million pages, F2 would be only 2.9e9.  Two
  random views land on the same page 0.008% of the time, as if all attention
  went to about 12,491 pages.  The plain mean of all 4,096 variables was 3.3%
  off; the median of 8 group means was 0.002% off (luck helps at that size).
- **DGIM**: hot lines are rare, so the counts are small and a percentage
  error looks large.  Across the 24 end-of-hour checks (last 1,000,000 lines
  each), the error ranged from 0.4% to 26.9%, inside DGIM's 50% guarantee.
  The stream order is dump order (sorted by wiki and title within each hour),
  not the order views happened.

### Finding: Week 7's DGIM estimate overcounts

The book (Section 4.6.3) adds every bucket whose newest one-bit is inside the
last k lines, but only *half* of the oldest such bucket.  Week 7's
`DGIM.estimate` adds that oldest bucket in full, then also half of the next
bucket even though it lies wholly outside the range.  On this day the Week 7
rule gave 692 for the last 1,000,000 lines (exact 461, 50.1% error) and 44 for
the last 100,000 (exact 23, 91.3%); the book rule gave 564 and 28.  Week 8 uses
the book rule in `SkippingDGIM.estimate` and reports the Week 7 rule beside it
(`week07_rule_estimate`).  Week 7's file is left unchanged here.

## DGIM 4.6.6

Placeholder: the reduced-error DGIM exercise (book Exercise 4.6.6) is added
in a separate change.
