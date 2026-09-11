# Week 1: Distributed File Systems and MapReduce Foundations

These notes summarize Sections 2.1 and 2.2 of *Mining of Massive Datasets*. The
assigned reading stops before Section 2.3, where specific MapReduce algorithms
begin.

The [SSH access guide](docs/ssh-access.md) records the Week 1 login procedure.
Continue to [Week 2](../week-02/README.md) for the cluster setup and word count.

## Why use a cluster?

A cluster combines many independent, relatively ordinary computers. It provides
more aggregate storage and computation than one machine, but it also increases
the likelihood that a node, disk, or network link will fail during a long job.
The system therefore has to treat failures as normal operating events.

The reading presents two complementary responses:

1. Store data redundantly so one failed component does not destroy the only
   copy.
2. Divide computations into tasks that can be rescheduled when a worker fails.

## Distributed file systems

A distributed file system is designed for files that are very large and are
typically read or appended rather than frequently modified in place. A file is
divided into large chunks, and copies of those chunks are placed on multiple
nodes. Distributing replicas across different failure domains helps preserve
availability when a node or network segment fails.

A master metadata service records the directory structure and the locations of
file chunks. In Hadoop's HDFS terminology, this role is the **NameNode**, while
the machines that store chunk data are **DataNodes**.

## MapReduce data flow

MapReduce separates application logic from the mechanics of parallel execution:

1. **Map:** Multiple map tasks process input elements or chunks in parallel and
   emit intermediate key-value pairs.
2. **Shuffle and grouping:** The framework partitions intermediate records,
   moves them to reducers, and groups every value associated with the same key.
3. **Reduce:** Each reducer processes a key and its collection of values, then
   emits zero or more output records.

The word-count example maps each observed word to `(word, 1)`. Grouping brings
all counts for the same word together, and reduction adds them to produce the
total.

## Combiners

A combiner performs safe local aggregation before mapper output crosses the
network. This can substantially reduce communication. It is only valid when the
operation can be regrouped and reordered without changing the answer; the
operation therefore needs the relevant associative and commutative properties.

## Parallelism and skew

Using more tasks can increase parallelism, but tasks also introduce scheduling,
startup, and intermediate-file overhead. Reducer workloads may be uneven when
some keys have far more values than others. This imbalance is called **skew** and
can leave a small number of reducers running long after the others finish.

## Failure recovery

The controller tracks task status and can reschedule failed work. If a map worker
fails, its completed map tasks may need to run again because their intermediate
files were stored locally. A failed reduce task can be assigned to another
worker and retrieve its inputs again. The simplified model in the reading treats
failure of the central controller as a job-level failure.

## Connection to the project

The planned cluster maps the reading to modern Hadoop components:

- HDFS NameNode and DataNodes provide distributed, replicated storage.
- YARN ResourceManager and NodeManagers allocate cluster resources.
- MapReduce jobs run parallel map and reduce tasks on top of that infrastructure.

The immediate engineering goal is to verify access and the machines' existing
state before installing anything. That preflight work tests whether the supplied
script's assumptions match the actual four-node environment.

## Week 1 environment status

On September 8, 2026, interactive and dedicated-key SSH access was verified for
the controller and all three workers. The checks were limited to account and
hostname identification. No Hadoop packages, services, storage, firewall rules,
SELinux settings, or system configuration were changed.

## Questions for the next meeting

- Where should the separate data disk be mounted on each VM?
- Are the controller and worker roles intended to be exclusive?
- What administrative privileges do student accounts have?
- Are firewall or SELinux changes authorized?
- Is the environment completely new, or does it contain an earlier Hadoop
  installation or HDFS data?
