# MinHash and LSH: a hand-worked walkthrough

A study guide for MMDS Chapter 3, "Finding Similar Items." Every number below
was checked with this week's code.

## The problem in one sentence

We have thousands of text passages and want the pairs that are nearly the same,
without comparing every pair to every other pair.

## Real-world analogy first

**Jaccard similarity.** Two friends each bring a guest list to a joint party.
Similarity = people on both lists / people on either list. Identical lists
score 1. Lists with nobody in common score 0.

**MinHash.** Shuffle the whole town's phone book at random. Walk down from the
top until you reach the first person who is on *either* guest list. Is that
person on *both* lists? The chance is exactly the similarity. Repeat with 100
different shuffles. The fraction of "yes" answers estimates the similarity, and
each list is now summarized by just 100 names.

**LSH.** Cut those 100 names into 25 groups of 4. File each list into a bin
using one group at a time. Two lists that land in the same bin for *any* group
get a closer look. Similar lists almost always share some bin; unrelated lists
almost never do. We only compare the lists that met in a bin.

## Step 1: shingles (Section 3.2)

A *k-shingle* is a run of k consecutive words. We use k = 2 here and k = 3 on
the real data. Four tiny documents:

| Doc | Text | 2-shingles |
| --- | --- | --- |
| D1 | the eagle has landed | the eagle, eagle has, has landed |
| D2 | the eagle has landed safely | the eagle, eagle has, has landed, landed safely |
| D3 | houston the eagle is go | houston the, the eagle, eagle is, is go |
| D4 | roger houston we copy | roger houston, houston we, we copy |

Exact Jaccard similarities (Section 3.1):

| Pair | Shared | Union | Jaccard |
| --- | ---: | ---: | ---: |
| D1, D2 | 3 | 4 | 0.75 |
| D1, D3 | 1 | 6 | 0.17 |
| D2, D3 | 1 | 7 | 0.14 |
| any pair with D4 | 0 | | 0 |

## Step 2: the characteristic matrix

One row per distinct shingle, one column per document. A 1 means "this
document contains this shingle."

| Row x | Shingle | D1 | D2 | D3 | D4 |
| ---: | --- | :-: | :-: | :-: | :-: |
| 0 | the eagle | 1 | 1 | 1 | 0 |
| 1 | eagle has | 1 | 1 | 0 | 0 |
| 2 | has landed | 1 | 1 | 0 | 0 |
| 3 | landed safely | 0 | 1 | 0 | 0 |
| 4 | houston the | 0 | 0 | 1 | 0 |
| 5 | eagle is | 0 | 0 | 1 | 0 |
| 6 | is go | 0 | 0 | 1 | 0 |
| 7 | roger houston | 0 | 0 | 0 | 1 |
| 8 | houston we | 0 | 0 | 0 | 1 |
| 9 | we copy | 0 | 0 | 0 | 1 |

Real data never stores this matrix. It is almost all zeros, so we keep each
document's set of rows instead.

## Step 3: two minhash rows by hand (Section 3.3)

Instead of truly shuffling the rows, use a hash function to give each row a
new position. With 10 rows, these two functions each reorder 0 to 9 with no
repeats:

| x | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
| --- | -: | -: | -: | -: | -: | -: | -: | -: | -: | -: |
| h1(x) = (3x + 1) mod 10 | 1 | 4 | 7 | 0 | 3 | 6 | 9 | 2 | 5 | 8 |
| h2(x) = (7x + 3) mod 10 | 3 | 0 | 7 | 4 | 1 | 8 | 5 | 2 | 9 | 6 |

A document's minhash value is the **smallest** h(x) over the rows it contains.

- D1 has rows {0, 1, 2}. h1 gives {1, 4, 7}, min **1**. h2 gives {3, 0, 7}, min **0**.
- D2 has rows {0, 1, 2, 3}. h1 gives {1, 4, 7, 0}, min **0**. h2 gives {3, 0, 7, 4}, min **0**.
- D3 has rows {0, 4, 5, 6}. h1 gives {1, 3, 6, 9}, min **1**. h2 gives {3, 1, 8, 5}, min **1**.
- D4 has rows {7, 8, 9}. h1 gives {2, 5, 8}, min **2**. h2 gives {2, 9, 6}, min **2**.

## Step 4: the signature matrix

| | D1 | D2 | D3 | D4 |
| --- | -: | -: | -: | -: |
| h1 | 1 | 0 | 1 | 2 |
| h2 | 0 | 0 | 1 | 2 |

Estimated similarity = fraction of rows that agree.

| Pair | Rows agreeing | Estimate | True Jaccard |
| --- | --- | ---: | ---: |
| D1, D2 | h2 | 0.5 | 0.75 |
| D1, D3 | h1 | 0.5 | 0.17 |
| D2, D3 | none | 0.0 | 0.14 |
| with D4 | none | 0.0 | 0.0 |

Two rows are far too few: D1 and D3 look as similar as D1 and D2. The error
shrinks like 1/sqrt(n). On the Apollo data we use n = 100 rows, so the typical
error is at most about 0.05.

## Why P(minhash values equal) = Jaccard

Look at two columns, A and B. Every row is one of three kinds:

- **X rows:** both columns have a 1 (the shared shingles).
- **Y rows:** exactly one column has a 1.
- **Z rows:** both have 0.

Shuffle the rows randomly and scan from the top. Z rows do not matter, because
neither document has them. The first row that is not Z decides both minhash
values. If it is an X row, both documents see it first and their values are
equal. If it is a Y row, only one of them has it, so their values differ.

Each non-Z row is equally likely to come first, so

P(equal) = X / (X + Y) = |A and B| / |A or B| = Jaccard(A, B).

Each minhash row is a coin flip that lands "equal" with probability J, so the
average over n rows estimates J.

## Step 5: banding into buckets (Section 3.4)

Split the signature into b bands of r rows. Here b = 2 and r = 1. Documents
with identical values in a band share a bucket for that band.

| Band | Bucket contents |
| --- | --- |
| band 1 (h1) | value 0: D2. value 1: **D1, D3**. value 2: D4 |
| band 2 (h2) | value 0: **D1, D2**. value 1: D3. value 2: D4 |

Candidate pairs are any two documents that share at least one bucket:
**(D1, D2)** and **(D1, D3)**. D1 and D2 are the true near-duplicates. D1 and
D3 are a *false positive*; checking candidates against their real similarity
removes it. D4 is never compared to anything. That saving is the whole point
of LSH.

## The S-curve

A pair with similarity s matches one band of r rows with probability s^r. It
misses all b bands with probability (1 - s^r)^b. So it becomes a candidate with
probability

P(candidate) = 1 - (1 - s^r)^b.

This rises steeply, like an S, near the threshold t = (1/b)^(1/r).

| b, r | Threshold | Effect |
| --- | ---: | --- |
| 20, 5 | 0.55 | balanced |
| 25, 4 | 0.45 | catches more true pairs, more false positives |
| 10, 10 | 0.79 | very few false positives, misses many moderate pairs |

More rows per band raise the threshold. More bands lower it. Pick a threshold
a little *below* the similarity you care about when missing a true pair costs
more than checking an extra candidate.

## How this maps to the code

| Idea | File |
| --- | --- |
| Words, shingles, stable 32-bit hash | `scripts/shingle.py` |
| h(x) = (a*x + b) mod (2^61 - 1), signatures, Jaccard | `scripts/minhash.py` |
| Bands, buckets, candidates, threshold, S-curve | `scripts/lsh.py` |
| Banding on Hadoop | `scripts/hadoop/` |

## Check yourself

1. Why must the shingle hash be the same on every machine?
2. If two windows have Jaccard 0.6, what is P(candidate) with b = 25, r = 4?
   (Answer: 1 - (1 - 0.6^4)^25, about 0.97.)
3. Why does LSH never compare D4 with anything?
