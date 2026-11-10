# Week 9: Memory Capacity and Shared Hadoop Jobs

Draft Wiki source. Publish from the reviewed branch after reconciliation.

The [Week 9 overview](https://github.com/batmandoescalc/big_data/blob/noah/week-09-capacity-concurrency/week-09/README.md)
contains commands, sanitized results and limitations.

Noah measured exact-set state growth under 128, 256 and 512 MiB process caps.
Two repetitions failed in the same checkpoint intervals: approximately
1.125–1.150 million, 2.350–2.375 million and 4.800–4.825 million unique 32-byte keys.
FM completed one million keys with about 15.1 MiB process RSS. These were
contained process failures, not observed VM crashes. Whole-VM thresholds in
the report are explicitly labeled extrapolations for this synthetic workload.

The Hadoop launcher was validated with one, two and four same-account jobs.
All seven applications succeeded and every 128-register output matched the
independent local baseline. Four submitted jobs completed in about 86 seconds,
with at most two application managers observed RUNNING. The cluster remained
healthy and all experimental inputs/outputs were preserved.

The actual two-user experiment remains for Noah and Max's November 11 session.
Max separately owns exact-versus-sketch algorithm timing, his HDFS setup and
the year of Wikipedia input. Larger 8/16/30-job stages remain unmeasured.
