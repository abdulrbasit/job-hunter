# Canonical location benchmark

Measured on Windows, Python 3.12.10, with `uv run python
scripts/benchmark_locations.py`. Values are microbenchmarks, so cold timings can
vary with filesystem cache and antivirus activity; throughput uses identical
inputs and repetition counts before and after the Phase 4 changes.

| Operation | Before | After | Change |
|---|---:|---:|---:|
| Cold `job_hunter.locations` import | 778.51 ms | 174.87 ms | 77.5% lower |
| First DE city resource load | 95.57 ms | 65.06 ms | 31.9% lower |
| First indexed DE lookup | 169.24 ms | 133.19 ms | 21.3% lower |
| 1,000 repeated exact lookups | 20,196.49 ms | 0.29 ms | >69,000x faster |
| 1,000 representative canonicalizations | 18,584.92 ms | 0.44 ms | >41,000x faster |
| 3,000 job allowlist gates | 15.61 ms | 12.58 ms | 19.4% lower |
| 1,000 company allowlist gates | 17,337.35 ms | 3.45 ms | >5,000x faster |
| One compatibility lookup without country evidence | 3,034.98 ms / 249 files | 1,197.25 ms / 249 files | 60.5% lower |
| Dashboard countries payload | 8,866 bytes | 8,866 bytes | unchanged |
| Default DE cities payload | 550,931 bytes | 11,554 bytes | 97.9% lower |

The production gates no longer use the global compatibility path for raw city
evidence. They constrain exact lookups to enabled countries, so the Munich +
Berlin allowlist loads only `DE.json`; a regression test checks one loaded city
resource and zero global-index builds. The global path remains for legacy tools
that have no country evidence.

The improvements come from cached exact canonicalization, normalized alias and
city-ID dictionaries per lazily loaded country, a cached set representation of
each enabled allowlist, and country-constrained custom-company matching. The
dashboard returns the first 250 population-ranked cities and searches the same
selected-country package resource on demand; an existing configured city is
always included by ID.
