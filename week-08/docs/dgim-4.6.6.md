## DGIM: reducing the error (section 4.6.6)

![Keeping more buckets per size shrinks DGIM's counting error](docs/dgim-4.6.6.svg)

### What the book says

DGIM counts the ones in the last N bits of a stream by keeping "buckets" of
sizes 1, 2, 4, 8, ... Week 7 used the basic rule: keep one or two buckets of
each size. Only the oldest bucket can stick out past the start of the range,
so the estimate counts it as half, and the answer can be off by up to 50%.

Section 4.6.6 lets each size keep r-1 or r buckets instead (sizes 1 and the
largest may keep 1 to r). When r+1 buckets of one size exist, the two oldest
merge into one bucket of double size, and that merge can ripple upward. With
more buckets of the smaller sizes, the one uncertain bucket is a smaller share
of the total, so the worst error falls to at most 1/(r-1). r=2 is the basic
algorithm.

### What we built and measured

- `scripts/dgim_reduced_error.py`: `DGIMReduced(window, r=2)`. Each size has
  its own queue, so a merge is a constant-time move, not a list rebuild.
  With r=2 it keeps exactly the same buckets and gives exactly the same
  estimates as Week 7's `DGIM` (tested step by step).
- `scripts/dgim_study.py`: one pass over each stream, every r side by side.
  Window N = 1,000,000 bits. 200 seeded query times x 60 range lengths k
  (log-spaced from 1 to N plus random ones), each compared with the exact
  count. Seed 4099.
- Real stream: one hour of Wikimedia pageviews
  (`pageviews-20261027-120000.gz`, 5,944,493 lines, sha256 `905b1795...`),
  one bit per line in file order, 1 when the page had at least 100 views:
  6,918 hot lines. Control stream: 3,000,000 seeded coin flips, p = 0.01.
- Every r is scored on the same queries: ranges holding at least 10 ones.
  The whole run takes about 8 seconds and 72 MB of RAM.

| r | Book worst case | Worst seen (Wikipedia / synthetic) | Average (Wikipedia / synthetic) | Buckets kept, max (Wikipedia / synthetic) |
| ---: | ---: | ---: | ---: | ---: |
| 2 (before) | 50% (basic analysis) | 48.1% / 49.3% | 12.9% / 12.6% | 20 / 23 (320 / 368 bytes) |
| 3 | 50% | 24.0% / 24.5% | 7.8% / 7.4% | 28 / 34 (448 / 544 bytes) |
| 5 | 25% | 12.5% / 12.5% | 4.2% / 4.0% | 45 / 55 (720 / 880 bytes) |
| 9 | 12.5% | 10.0% / 10.0% | 2.3% / 2.2% | 74 / 90 (1,184 / 1,440 bytes) |

Memory counts 16 bytes per bucket, as in Week 7. The 1/(r-1) bound held on
every scored query for every r, on both streams.

### The trade-off

Going from r=2 to r=9 cuts the average error about 5.5 times (12.9% to 2.3%)
and the worst error about 5 times, while the summary grows about 4 times
(20 to 74 buckets, still about 1 KiB for a million-bit window). Each step of
r buys less: the error falls like 1/r, while the memory grows like r.

**In one sentence:** keeping a few more buckets of each size lets DGIM
answer "how many in the last million?" within a few percent instead of within
half, for about a kilobyte of memory.

### A bug this found in Week 7

Week 7's estimate counted every in-range bucket in full, then added half of
the next bucket, whose bits had all expired. The book halves the oldest
in-range bucket instead. Example: eight ones, window 5, exact count 5. The
old rule said 8 (60% off, above the promised 50%); the book's rule says 6.
On this study's queries the old rule averaged 62% error, worst 197%. Week 7
now uses the book's rule, and its 10,000-event run moved from 46 (31.43%
error) to 38 (8.57%), exact 35. The study keeps the old rule only as a
labelled comparison (`week7_original_estimate`, Week 7 before the fix,
commit 141deb1).

### Honest edge cases

- **Very small counts.** The book's argument assumes the half-counted bucket
  has size 2 or more. If it has size 1, the range holds at most r ones, and
  counting that single one as half can still be 50% off (for example, true
  count 1, estimate 0.5). This happened on 1,202 Wikipedia and 1,174
  synthetic queries, for every r. They are reported separately, not in the
  table. A common fix is to count a size-1 boundary bucket in full, since it
  is exact, but that is not the book's rule, so it was not applied.
- **The 1/(r-1) formula is loose at r=2.** It gives 100% there; the basic
  analysis in section 4.6.4 gives the tighter 50%, and we never saw more
  than 49.3%.
- The pageviews file is sorted by project and title, not by time, so "the
  last N lines" is a stand-in for "the last N events". It is still a real,
  bursty mix of hot and cold pages.

### Reproduce

```bash
# Download once (about 52 MB; the data folder is ignored by Git):
mkdir -p data/week-08/dgim-sample
curl -fL -A "big_data-coursework/1.0" \
  -o data/week-08/dgim-sample/pageviews-20261027-120000.gz \
  https://dumps.wikimedia.org/other/pageviews/2026/2026-10/pageviews-20261027-120000.gz

python3 week-08/scripts/dgim_study.py \
  --pageviews data/week-08/dgim-sample/pageviews-20261027-120000.gz \
  --output data/week-08/results/dgim-study.json \
  --chart week-08/docs/dgim-4.6.6.svg
```

Flags: `--window`, `--rs`, `--threshold`, `--query-times`, `--k-values`,
`--synthetic-length`, `--synthetic-p`, `--seed`, `--max-lines`. Leave out
`--pageviews` to run the synthetic stream alone.
