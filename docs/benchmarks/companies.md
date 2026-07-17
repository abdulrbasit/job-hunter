# Company store benchmark

Measured on Windows with Python 3.12.10 using `uv run python
scripts/benchmark_companies.py` against 100,000 synthetic rows spread across
3 countries (~33,334 rows/country, ~33% enabled — a deliberately pessimistic
opt-in rate; real workspaces enable dozens to low hundreds of companies per
country, not thousands). "Before" is one run prior to the Phase 4 change;
"After" is the median of three runs.

| Operation | Before | After | Change |
|---|---:|---:|---:|
| Import 100k rows (`executemany`, single transaction) | 464 ms | 466 ms | unchanged (already fast) |
| `candidate_companies()` — one country, one industry excluded, ~27.8k matching rows | 172.4 ms | 148.2 ms | 14% lower |
| `query_page()` — first page (country filter, page_size=50) | 20.0 ms | 20.3 ms | unchanged |
| `query_page()` — last page (page 667, same filter) | 66.1 ms | 68.1 ms | unchanged |

## What changed

`candidate_companies()` selected with `ORDER BY source DESC, id` so the
Python-side dedup (prefer a user's own target over a catalog row with the
same URL) could rely on "user rows come first." At 100k rows/country that
`ORDER BY` isn't covered by any index, so SQLite built a temp b-tree to sort
every matching row before returning them —
confirmed via `EXPLAIN QUERY PLAN`:

```
before: SEARCH companies USING INDEX idx_companies_country (country=?) | USE TEMP B-TREE FOR ORDER BY
after:  SEARCH companies USING INDEX idx_companies_country (country=?)
```

The query now fetches unordered (the `country`/`industry` filters already use
`idx_companies_country`/`idx_companies_industry` — a `SEARCH`, never a table
`SCAN`), and the preference logic runs in Python instead: catalog rows
populate a dict keyed by `(normalized_url, country)` first, then user rows
overwrite it. Same result, no SQL-side sort.

The remaining ~148 ms is dominated by converting ~27.8k `sqlite3.Row` objects
to `dict` and building the preference dict in Python — proportional to how
many companies are enabled, not the table size. At a realistic enabled count
(dozens to hundreds per country, since catalog rows are opt-in), this drops
to low single-digit milliseconds; the benchmark's 33%-enabled rate exists to
report a real worst case, not a representative one.

## What we did not change

- **Import** was already sub-second for 100k rows (well under the "seconds"
  target) via `executemany` in one transaction — no further work needed.
- **Pagination** (`query_page`) stays on `LIMIT`/`OFFSET`. The deep-page case
  (offset ~33,300) is ~3.3x the first-page cost but still under 70 ms —
  nowhere near bad enough to justify keyset pagination's added complexity
  (cursor state across the store, the dashboard API, and `dashboard.js`).
- **`COUNT(*)` per page turn**: `query_page()` runs one `COUNT` and one
  `SELECT` per call. Caching the count at the API layer would need
  invalidation on every filter change and every store mutation for a
  single-digit-millisecond saving — not worth the added state.
- **A partial index** (`(country) WHERE enabled = 1`) was considered per the
  original plan, but `EXPLAIN QUERY PLAN` already shows `country` queries as
  index `SEARCH`, never a full-table `SCAN` — the bottleneck was the sort,
  not the filter, so a partial index would not have moved the number.
