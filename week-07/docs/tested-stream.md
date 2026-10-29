# Hand-checkable tested stream

This eight-event stream makes the Week 7 tests and results visible without
requiring a large generated file. The same values appear in
`DocumentedStreamTests.test_all_four_sketches_on_documented_stream`.

| Event | User | Status | DGIM error bit |
| ---: | --- | ---: | ---: |
| 1 | alice | 200 | 0 |
| 2 | bob | 500 | 1 |
| 3 | alice | 200 | 0 |
| 4 | carol | 200 | 0 |
| 5 | bob | 500 | 1 |
| 6 | alice | 500 | 1 |
| 7 | dana | 200 | 0 |
| 8 | alice | 500 | 1 |

## Exact answers

- Distinct users: **4** (`alice`, `bob`, `carol`, `dana`).
- User counts: `alice=4`, `bob=2`, `carol=1`, `dana=1`.
- Second moment: **22**, because `4² + 2² + 1² + 1² = 22`.
- Error bits in the eight-event window: **4**.

## Sketch results

These results use 256 Bloom-filter bits with four hashes, 16 FM registers, 64
AMS estimators with seed 4099, and an eight-event DGIM window.

| Technique | Result | Exact comparison | Logical memory |
| --- | ---: | ---: | ---: |
| Bloom filter | All four inserted users present; no false negatives | Expected behavior | 32 bytes |
| Flajolet--Martin | 4.298 distinct users | 4 exact (7.45% high) | 16 bytes |
| AMS | 22.75 second moment | 22 exact (3.41% high) | 1,024 bytes |
| DGIM | 4 recent errors | 4 exact | 48 bytes |

FM's register array is
`[2, 4, 3, 1, 1, 4, 1, 4, 1, 1, 2, 2, 2, 2, 2, 1]`. In the Hadoop
version, each mapper computes such trailing-zero maxima for its own partition;
the reducer takes the maximum for each register across mapper arrays.

This tiny example proves the data flow and expected answers. The larger
10,000-to-50,000-event experiments in the Week 7 README provide the more
meaningful accuracy and memory comparison.
