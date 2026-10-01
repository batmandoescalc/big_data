# Week 4 dataset: Apollo 11 transcript windows

## Why this data

The three Apollo 11 transcripts from Week 2 contain real near-duplicates.
NASA's Public Affairs Office (PAO) commentary often replays air-to-ground
exchanges for the press, so the same words appear in two documents with small
differences in punctuation, speaker labels, and transcription. That is exactly
the "similar, not identical" case that shingling and minhash are built for.

Example from the files:

| File | Text |
| --- | --- |
| air-to-ground | Houston, Tranquility Base here. THE EAGLE HAS LANDED. |
| onboard-voice | Houston - Tranquility Base here. THE EAGLE HAS LANDED. |
| public-commentary | Houston, Tranquility base here. The Eagle has landed. |

The data was already downloaded, checksummed, and stored in HDFS in Week 2.
Nothing was downloaded again.

| Location | Contents |
| --- | --- |
| `data/apollo11/text/` (ignored) | The three UTF-8 transcripts |
| `/datasets/apollo11/2026-09-11/text` | The same files in HDFS |

## From files to windows

Whole files are too coarse: every pair of files would look partly similar. We
split each file into fixed **windows of 50 words** and compare windows.

1. Words follow the Week 2 rules: lowercase letters with internal apostrophes.
   Numbers, timestamps, and punctuation are separators, so formatting
   differences between transcripts disappear.
2. A window starts every 25 words (stride 25). A last window is added at the
   end of each file so no words are left out.
3. Each window is named `file:start`, where `start` is its first word's
   position, for example `air-to-ground:012925`.

| File | Words | Windows |
| --- | ---: | ---: |
| air-to-ground | 129,454 | 5,178 |
| onboard-voice | 41,280 | 1,651 |
| public-commentary | 184,306 | 7,372 |
| **Total** | **355,040** | **14,201** |

The 355,040 words match the Week 2 word count exactly.

## Why 50 words and stride 25

**Window size.** 50 words is a few spoken exchanges: long enough that an
accidental match is unlikely, short enough that a replayed passage fills most
of a window.

**Stride.** Two copies of a passage rarely start at the same offset in both
files, so their windows are misaligned by some number of words m. With 50-word
windows and word 3-shingles, the two windows share 48 - m of their 48 shingles
each, so

J = (48 - m) / (48 + m).

Stride S keeps m at most S/2 for the best-aligned pair of windows:

| Stride | Worst m | Worst J for a long exact replay | Windows | Pairs sharing a shingle |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 5 | 0.81 | 35,493 | 45.6 million |
| **25** | **12** | **0.60** | **14,201** | **7.3 million** |
| 50 | 25 | 0.32 | 7,103 | 1.8 million |

"Long" means at least window + stride words (75 for stride 25), so a whole
window from each file fits inside the replay. Stride 25 keeps every such
replay at 0.60 or higher, a safe margin over our 0.5 near-duplicate threshold.
Stride 50 can drop a real replay to 0.32. Stride 10 costs 2.5 times the
windows and 6 times the exact-comparison work.

We measured what that costs in coverage. Counting public-commentary words that
sit in a window with a cross-file match of Jaccard 0.5 or more:

| Stride | Public-commentary words covered |
| ---: | ---: |
| 10 | 76,020 |
| 25 | 47,775 |
| 50 | 20,250 |

Stride 10 finds noticeably more. The difference is mostly short replays (under
75 words) and edited passages, which a 50-word window only matches when it
happens to be well aligned. We kept stride 25 because it meets the guarantee
above for full replays and matches the assignment's starting point. Stride 10
is the better choice if short replays matter; on this 2.2 MB dataset it would
still finish in about a minute locally.

## Pairs we ignore

Windows from the same file that overlap (start less than 50 words apart) share
words by construction. They are excluded from the ground truth, the candidates'
evaluation, and every reported number. Same-file pairs that do *not* overlap are
kept; the 166 such pairs at Jaccard 0.5 or above are mostly repeated page
headers such as "rest period, no communications."

## Known limitations

- Speaker labels (`CC`, `CDR`) and page headers stay in the text, which lowers
  the similarity of replayed passages a little.
- OCR errors are kept as they are, matching earlier weeks.
- 2.2 MB is a learning dataset. It shows correctness, not scale.
