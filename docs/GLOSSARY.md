# Glossary

Short definitions of the terms used across the weekly READMEs, in the order a
new reader usually meets them. Each entry names the week where the idea is put
to work. For the full cross-week index of scripts and results, see the
[repository guide](REPOSITORY_GUIDE.md).

## Cluster and Hadoop

| Term | Meaning in this repository | Week |
| --- | --- | --- |
| Controller | The one VM that coordinates the cluster. It runs the NameNode and ResourceManager and does no data processing. | 1-2 |
| Worker | One of the three VMs that store data and run tasks. Each runs a DataNode and a NodeManager. | 1-2 |
| HDFS | Hadoop Distributed File System. Splits files into large blocks and stores them across the workers. | 1-2 |
| Block | The unit HDFS stores and replicates. A mapper usually processes one block's worth of input. | 1-2 |
| NameNode | Controller service that records which blocks make up each file and which workers hold them. It stores metadata, not file contents. | 2 |
| DataNode | Worker service that stores the actual blocks and serves them to tasks. | 2 |
| Replication factor | How many copies HDFS keeps of each block. The installer sets this cluster to 2, so one worker can fail without losing data. | 2 |
| YARN | Yet Another Resource Negotiator. Decides which worker gets how much CPU and memory for each job. | 2 |
| ResourceManager | Controller service that accepts jobs and allocates containers across the workers. | 2 |
| NodeManager | Worker service that launches and monitors containers on its machine. | 2 |
| Container | A bounded slice of a worker's CPU and memory in which one map or reduce task runs. | 2-4 |

## MapReduce

| Term | Meaning in this repository | Week |
| --- | --- | --- |
| Mapper | Reads input records and emits key-value pairs, for example `(word, 1)`. | 2 |
| Shuffle and sort | The framework step that moves every pair with the same key to the same reducer, sorted by key. Usually the most expensive network step. | 1-2 |
| Reducer | Receives one key with all of its values and produces the final output for that key, for example a sum. | 2 |
| Combiner | Optional local reducer run on mapper output before the shuffle to shrink network traffic. Not used in the first word count; Week 5's one-job join uses one to pre-sum counts. | 1-2, 5 |
| Hadoop Streaming | Lets mappers and reducers be any program that reads stdin and writes stdout, which is how this study uses Python. | 2 |
| Reduce-side join | Both relations are tagged and shuffled by the join key; the reducer matches them. Needs buffering because value order is not guaranteed. | 3 |
| Map-side (replicated) join | A small table is copied to every mapper and joined in memory, so no reducer buffer or extra shuffle is needed. | 5 |
| Fixed overhead | Time a Hadoop job spends on JVM startup, YARN scheduling, and shuffling regardless of input size. Explains why SQLite wins on small inputs. | 3-5 |

## Similar items

| Term | Meaning in this repository | Week |
| --- | --- | --- |
| Jaccard similarity | Size of the intersection divided by size of the union of two sets. | 4 |
| Shingle | A run of k consecutive words (or characters) from a document. A document becomes its set of shingles. | 4 |
| Shingle hash | Each shingle mapped to a stable 32-bit integer with crc32, never Python's salted `hash()`. Saves memory and keeps Hadoop tasks consistent. | 4 |
| Minhash signature | A short list of n minimum hash values per document. The fraction of matching positions estimates Jaccard similarity, so the full shingle set can be dropped. | 4 |
| Band and row | LSH splits each signature into b bands of r rows. Two documents become candidates if any whole band matches. | 4 |
| Candidate pair | A pair LSH proposes for checking. Only candidates are compared, avoiding all-pairs comparison. | 4 |
| S-curve and threshold | The probability that a pair becomes a candidate, `1 - (1 - s^r)^b`, rises sharply near `(1/b)^(1/r)`. Choosing b and r trades false positives against false negatives. | 4 |
| Ground truth | The exact answer computed independently, used to measure what LSH found and missed. | 4 |

## Evidence and comparison

| Term | Meaning in this repository | Week |
| --- | --- | --- |
| Local reference | An independent non-Hadoop implementation (local scan or SQLite) whose output Hadoop must match exactly. | 2-5 |
| Canonicalized output | Results sorted and normalized so two implementations can be compared for exact equality. | 3, 5 |
| Median ratio | Median Hadoop runtime divided by median SQLite runtime at one input size; 1.0 would mean equal speed. | 5 |
| Spark | A newer engine that keeps intermediate data in memory between steps and usually runs on HDFS and YARN. Discussed as an estimate, not yet measured here. | 3, 5 |
