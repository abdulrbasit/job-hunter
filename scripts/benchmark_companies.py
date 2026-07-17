"""Repeatable benchmarks for the company store: bulk import, candidate selection, pagination.

Generates synthetic rows (the bundled seed today is ~3.9k rows across 61 countries —
too small to stress-test 100k-per-country scale) directly against the same schema
`job_hunter.companies.store` creates, then measures the hot paths a real workspace
would hit: importing a country's worth of catalog data, selecting hunt candidates,
and paginating the dashboard's Companies table.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_INDUSTRIES = ("software_it", "finance", "manufacturing", "retail_ecommerce", "consulting", "other")


def _elapsed_ms(operation: Callable[[], Any], repetitions: int = 1) -> float:
    started = time.perf_counter()
    for _ in range(repetitions):
        operation()
    return (time.perf_counter() - started) * 1_000


def _synthetic_rows(count: int, countries: list[str]) -> list[tuple[Any, ...]]:
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    rows = []
    for i in range(count):
        name = f"Company {i}"
        url = f"https://company{i}.example/careers"
        rows.append(
            (
                f"synthetic-{i}",
                name,
                name.casefold(),
                url,
                url.rstrip("/").lower(),
                countries[i % len(countries)],
                _INDUSTRIES[i % len(_INDUSTRIES)],
                "catalog",
                "benchmark",
                1 if i % 3 == 0 else 0,  # ~33% enabled, matching real opt-in scale
                now,
                now,
            )
        )
    return rows


def _import_rows(root: Path, rows: list[tuple[Any, ...]]) -> float:
    from job_hunter.companies import store

    store.company_count(root)  # ensures schema/indexes exist before timing the insert itself

    def run() -> None:
        conn = sqlite3.connect(store.db_path(root))
        try:
            with conn:
                conn.executemany(
                    """INSERT INTO companies
                       (catalog_id, name, normalized_name, url, normalized_url, country, industry,
                        source, batch, enabled, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    rows,
                )
        finally:
            conn.close()

    return _elapsed_ms(run)


def _explain_plan(root: Path, sql: str, params: list[Any]) -> str:
    from job_hunter.companies import store

    conn = sqlite3.connect(store.db_path(root))
    try:
        rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()  # noqa: S608
    finally:
        conn.close()
    return " | ".join(str(row) for row in rows)


def main() -> None:
    from job_hunter.companies import store

    countries = ["DE", "US", "FR"]
    row_count = 100_000

    with tempfile.TemporaryDirectory(prefix="job-hunter-bench-companies-") as tmp:
        root = Path(tmp)
        rows = _synthetic_rows(row_count, countries)
        import_ms = _import_rows(root, rows)

        candidate_sql = "SELECT * FROM companies WHERE enabled = 1 AND country IN (?) AND industry NOT IN (?)"
        candidate_plan = _explain_plan(root, candidate_sql, ["DE", "finance"])
        candidate_ms = _elapsed_ms(
            lambda: store.candidate_companies(root, countries=["DE"], excluded_industries=["finance"]), 20
        )

        page_shallow_ms = _elapsed_ms(lambda: store.query_page(root, country="DE", page=1, page_size=50), 20)
        pages_total = store.query_page(root, country="DE", page=1, page_size=50)["pages"]
        page_deep_ms = _elapsed_ms(lambda: store.query_page(root, country="DE", page=pages_total, page_size=50), 20)

        result = {
            "row_count": row_count,
            "countries": countries,
            "import_executemany_single_txn_ms": import_ms,
            "candidate_companies_query_plan": candidate_plan,
            "candidate_companies_20x_total_ms": candidate_ms,
            "candidate_companies_avg_ms": candidate_ms / 20,
            "query_page_shallow_first_page_20x_avg_ms": page_shallow_ms / 20,
            "query_page_deep_last_page_20x_avg_ms": page_deep_ms / 20,
            "query_page_total_pages_for_DE": pages_total,
        }
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
