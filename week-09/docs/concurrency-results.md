# November 11: two-user Hadoop results

No more stress runs are planned. Evidence: [joint-session-summary.json](../results/joint-session-summary.json).

## Eight jobs: four per account

All eight YARN jobs succeeded. Noah's four outputs matched the independent 128-register baseline; Max should retain his output verification.

Snapshots showed at most two applications RUNNING and six waiting. Peak allocation was six vcores and 6,144 of 12,288 MiB. FIFO ordering and a 2,048 MiB application-manager budget were confirmed. Allocated cores alone do not prove CPU was the sole bottleneck.

Jobs reached YARN 17.6–19.4 seconds after the agreed start. The last finished 165.6 seconds after that start. Noah's client turnaround was 46–108 seconds and observed application-manager wait was 32–81 seconds. These are not task execution times.

Max separately reported execution under 40 seconds and a longest wait of 118 seconds. His roughly 20-seconds-per-extra-job rule is a small-sample prediction. Consecutive Noah IDs followed by Max IDs fit submission-order scheduling, rather than alternating users.

## Thirty submissions: fifteen per account

Saved YARN records confirm thirty submissions from two identities. Noah's RAM guard interrupted his stage. A follow-up controller check showed 107 MiB swap use and one-minute load 12.31. The guard did not retain the triggering node or exact minimum memory.

| Account | Submitted | Succeeded | Canceled |
| --- | ---: | ---: | ---: |
| Noah | 15 | 1 | 14 |
| Max | 15 | 15 | 0 |

The initial cancellation snapshot missed late-arriving IDs. Reconciliation matched Noah's exact stage names and owner, then canceled fourteen remaining jobs. Max's jobs were untouched.

This is an interrupted thirty-submission experiment, not thirty successful completions or thirty simultaneously executing jobs. Submission clients and monitoring use controller resources outside the YARN task budget. This round did not validate the smaller-round linear prediction.

## Closeout and remaining work

Final snapshot: zero active applications, three active workers, about 5.5 GiB controller available RAM and 86 MiB still swapped. Results and failed attempts were preserved. Cluster configuration was unchanged.

Noah's experimental evidence is ready for review: capped memory and VM estimates, successful two-user work, and effects/failure of thirty submissions. No separate bandwidth benchmark is required by issue #24. Matt can decide whether he wants a later repeat.

Max owns the four-algorithm comparison and year of Wikipedia data and should confirm completion with evidence. Both students should review and explain the write-up. PR #25 remains draft and unmerged. The late-ID abort-cleanup limitation must be fixed before future large bursts; no additional runs are planned now.
