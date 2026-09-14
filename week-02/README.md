# Week 2: Examples of MapReduce Algorithms

## Week 2 objectives

- Review Section 2.3 of *Mining of Massive Datasets* ("Algorithms Using MapReduce").
- Get Hadoop onto the virtual machines and test it.
- Find an interesting source of text data to store on the machines.
- Code the word-count example for MapReduce and run it on that data.

The practical work this week connected Week 1's distributed-storage and MapReduce concepts to a working cluster and a real text dataset.

## Week 2 files

- [Program walkthrough](docs/apollo11-wordcount.md): start here to understand what we built.
- [Word-count code](scripts/wordcount/): our mapper, reducer, and Hadoop launcher.
- [Dataset notes](docs/datasets/apollo11.md) and [downloader](scripts/fetch_apollo11.py).
- [Cluster setup](docs/cluster-setup.md), [installer](hadoop-poc-rhel9.sh), and [verification script](scripts/verify-cluster.sh).
- [Tests](tests/), [current status](docs/STATUS.md), and [handoff](docs/HANDOFF.md).

Run commands in the supporting docs from the repository root unless they specify a controller session.

## Environment progress

Hadoop 3.4.3 and Java 11 were installed on the four RHEL 9 virtual machines. The controller runs the HDFS NameNode and YARN ResourceManager. Each of the three workers runs a DataNode and NodeManager.

During setup:

- The assigned data disks were prepared and mounted at `/data`.
- Hadoop services were configured to start automatically.
- Network rules were restricted to the required communication between cluster nodes.
- All three HDFS workers and all three YARN workers registered successfully.
- Hadoop's bundled word-count example passed a small initial test, returning `cat: 6` and `dog: 3`.

That initial test established that the cluster worked before running our own program.

## Text dataset: Apollo 11 transcripts

We selected three transcripts from NASA's [Apollo 11 transcript collection](https://www.nasa.gov/wp-content/uploads/static/history/alsj/a11/a11trans.html):

| Transcript | Content |
| --- | --- |
| [Technical air-to-ground](https://www.nasa.gov/wp-content/uploads/static/history/alsj/a11/a11transcript_tec.html) | Communications between the spacecraft and ground teams |
| [Public Affairs Office commentary](https://www.nasa.gov/wp-content/uploads/static/history/alsj/a11/a11transcript_pao.html) | Public commentary explaining the mission's progress |
| [Command module voice](https://www.nasa.gov/wp-content/uploads/static/history/alsj/a11/a11transscript_cm.html) | Voices recorded aboard the command module |

The September 11, 2026 snapshot contains 2,221,376 bytes of extracted text, about 2.2 MB. These conversations provide recognizable words such as `houston`, `apollo`, and `eagle`, making the results easy to inspect.

The downloader retained the original HTML, extracted UTF-8 text, and a manifest recording sources and checksums. Two source pages required Windows-1252 decoding before conversion to UTF-8.

The files were stored in HDFS with two replicas per block. Readback checksums matched the local files, and HDFS reported healthy storage. The word-count job used only the extracted text, excluding the original HTML and manifest.

## Defining a word

The counting rules are explicit:

- Convert text to lowercase and count sequences of English letters.
- Keep apostrophes inside words, so `you're` remains one word.
- Treat numbers and other punctuation as separators. `Apollo 11` produces `apollo`; `air-to-ground` produces three words.
- Include speaker labels, document headers, and common words such as `the`.
- Leave transcription and OCR errors unchanged.

The results therefore describe the extracted documents, including their labels and headers, rather than only spoken dialogue.

## Our MapReduce implementation

We wrote two Python programs and used Hadoop Streaming to run them as mapper and reducer tasks.

### Map

`mapper.py` reads each input line, applies the word rules, and emits `(word, 1)` for every occurrence.

### Shuffle and grouping

Hadoop sorts and groups the mapper output so that records for the same word reach the reducer together.

### Reduce

`reducer.py` adds the counts for each word and writes its total. It holds only the current word and its running count in memory.

For example:

```text
Input:    Houston Houston Eagle
Map:      (houston, 1), (houston, 1), (eagle, 1)
Group:    eagle → [1], houston → [1, 1]
Reduce:   (eagle, 1), (houston, 2)
```

Hadoop supplies the distributed execution and grouping. Our Python programs supply the word extraction and addition. This first version uses one reducer and no combiner.

## Running and checking the program

Before submission, we confirmed that all three workers were online and Python was available on every node. The small local example produced the expected counts.

The Apollo 11 job then completed through YARN with three launched mapper tasks and one reducer. Results were saved to a new HDFS directory, preserving the input and earlier results.

To verify correctness, a separate local program scanned the transcript characters and counted words independently. Every word and count matched the Hadoop output. All 20 repository tests passed, including five tests for the new word-count programs.

## Results

The completed run counted **355,040 word occurrences** and **8,184 distinct words**.

| Word | Count |
| --- | ---: |
| the | 16,597 |
| houston | 4,487 |
| apollo | 3,808 |
| eagle | 1,655 |
| tranquility | 739 |
| moon | 303 |

These totals depend on the stated word rules. They differ from simply counting whitespace-separated items, which would also include timestamps and numbers.

## Week 2 outcome

The cluster setup, dataset preparation, and custom word-count exercise are complete. HDFS stores the replicated input and results, YARN allocates resources, and MapReduce runs our Python processing across the cluster.

This small dataset demonstrates correctness and distributed execution. It does not establish performance at large scale or verify failure recovery. Larger datasets and controlled performance experiments remain later work.
