# Flajolet-Martin is the one streaming algorithm run on Hadoop

Of the four Chapter 4 algorithms implemented locally, only Flajolet-Martin is
run as a Hadoop job. Each partition can be summarized independently and the
register arrays merge exactly with `max`, which is associative and
commutative, so the distributed answer equals the single-process answer. AMS
would need a coordinated sampling design to keep correct global probabilities,
and DGIM depends on global event order that unordered MapReduce partitions do
not preserve. A Bloom filter also merges cleanly, but answers membership
rather than giving a numeric statistic to check. FM was chosen as the clearest
demonstration, not as the best streaming algorithm in general.
