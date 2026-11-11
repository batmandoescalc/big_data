# Map-side replicated join when one relation is small

From Week 5 on, a join between a large fact relation and a small dimension
table loads the dimension table into every mapper through Hadoop's distributed
cache and joins each fact row immediately. The Week 3 reduce-side join had to
buffer every fact row for a key until its dimension record arrived, because
Hadoop does not order values within a key; one popular key could exhaust a
reducer's memory. The map-side design also removed a whole job and cut the
observed Apollo query from about 95 to about 47 seconds.

This does not cover a join of two large relations. A dimension table too big
to copy into every mapper still needs a partitioned or reduce-side strategy.
