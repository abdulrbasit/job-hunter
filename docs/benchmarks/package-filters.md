# Package filter benchmark

Measured on Windows with Python 3.12.10 using three runs of `uv run python
scripts/benchmark_filters.py`. The table reports median timings before and after
the Phase 4 change.

| Operation | Before | After | Change |
|---|---:|---:|---:|
| Cold package import | 222.13 ms | 209.66 ms | 5.6% lower |
| Build 1,000 identical filter sets | 108.74 ms | 19.79 ms | 81.8% lower |
| 100,000 exact language matches | 22.12 ms | 20.45 ms | 7.6% lower |
| 100,000 title contains matches | 71.77 ms | 65.52 ms | 8.7% lower |
| 100,000 company-normalized matches | 257.00 ms | 269.06 ms | noise / unchanged |
| 100,000 taxonomy-expanded matches | 23.73 ms | 24.25 ms | noise / unchanged |

Construction was the only material repeated cost: each load rebuilt the same
regular expressions and exact sets from unchanged user choices. Phase 4 caches
up to 256 immutable matchers by package filter type and scalar choice tuple.
Exact filters retain a prebuilt `frozenset` and no longer compile an unused
regular expression. Matching itself was already compiled and fast, so its code
path was not changed.
