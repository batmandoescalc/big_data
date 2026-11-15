# Every cluster result must exactly match an independent local reference

A Hadoop result is not reported until it equals the output of a separate
single-machine implementation (plain Python or SQLite) on the same prepared
input, after normalizing row order. A distributed job can succeed and still be
wrong: the first Week 3 join reducer exited cleanly while emitting 4,705 of
8,420 rows. Exact comparison catches that, and it gives each runtime
measurement a single-machine baseline. Estimates from approximate algorithms
are compared against an exact answer instead, with the error reported.
