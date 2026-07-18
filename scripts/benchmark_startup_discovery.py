"""Repeatable synthetic benchmark for startup fan-out, dedup, and feed queries."""

from __future__ import annotations

import json
import statistics
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path

from job_hunter.models import JobPosting
from job_hunter.sources.boards.registry import BOARD_REGISTRY
from job_hunter.sources.orchestrator import _dedup_text, deduplicate_company_titles
from job_hunter.sources.search import canonicalize_url
from job_hunter.tracking.repository import _conn


def _timed(callable_, repeats: int = 5) -> float:
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        callable_()
        samples.append((time.perf_counter() - started) * 1000)
    return statistics.median(samples)


def _jobs() -> list[JobPosting]:
    jobs = []
    for company_id in range(500):
        company = f"Company {company_id} GmbH"
        for role_id in range(4):
            title = f"Product Manager {role_id}"
            jobs.append(JobPosting(title=title, company=company, url=f"https://one.test/{company_id}/{role_id}"))
            jobs.append(
                JobPosting(
                    title=f"{title} (m/f/d)",
                    company=f"COMPANY {company_id}",
                    url=f"https://two.test/{company_id}/{role_id}",
                )
            )
    return jobs


def _global_scan(postings: list[JobPosting]) -> None:
    kept: list[tuple[str, str]] = []
    for posting in postings:
        company = _dedup_text(posting.company, company=True)
        title = _dedup_text(posting.title)
        if any(
            other_company == company and SequenceMatcher(None, title, other).ratio() >= 0.92
            for other_company, other in kept
        ):
            continue
        kept.append((company, title))


def _feed_query_metrics() -> dict[str, float | str]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with _conn(root) as conn:
            now = "2026-07-18T00:00:00+00:00"
            conn.executemany(
                """INSERT INTO jobs (url, canonical_url, status, title, company, company_type, discovered_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        f"https://example.test/{index}",
                        f"https://example.test/{index}",
                        "candidate" if index % 4 else "discarded",
                        f"Role {index}",
                        f"Company {index % 500}",
                        "startup" if index % 5 == 0 else "enterprise",
                        now,
                    )
                    for index in range(30_000)
                ],
            )
            query = """SELECT id FROM jobs WHERE status IN ('candidate', 'discovered')
                       AND company_type = 'startup'
                       ORDER BY COALESCE(discovered_at, created_at) DESC, id DESC LIMIT 50"""
            conn.execute("DROP INDEX IF EXISTS idx_jobs_status_company_type")
            before = _timed(lambda: conn.execute(query).fetchall(), 30)
            plan_before = " | ".join(str(tuple(row)) for row in conn.execute(f"EXPLAIN QUERY PLAN {query}"))
            conn.execute("CREATE INDEX idx_jobs_status_company_type ON jobs(status, company_type)")
            after = _timed(lambda: conn.execute(query).fetchall(), 30)
            unique_url = any(
                row[2] and [item[2] for item in conn.execute(f"PRAGMA index_info('{row[1]}')")] == ["canonical_url"]
                for row in conn.execute("PRAGMA index_list(jobs)")
            )
    return {
        "feed_before_ms": round(before, 3),
        "feed_composite_index_ms": round(after, 3),
        "feed_improvement_percent": round((before - after) / before * 100, 1),
        "feed_plan_before": plan_before,
        "canonical_url_unique_index": str(unique_url).lower(),
    }


def main() -> None:
    jobs = _jobs()
    urls = [f"https://example.test/jobs/{index % 10_000}?utm_source={index}" for index in range(50_000)]
    adapters = [adapter() for adapter in BOARD_REGISTRY.values() if adapter.startup_source]
    countries = ("DE", "US", "FR")
    fanout = sum(
        1 if getattr(adapter, "once_per_run", False) else sum(adapter.supports_country(code) for code in countries)
        for adapter in adapters
    )
    result: dict[str, object] = {
        "postings": len(jobs),
        "bucketed_fuzzy_ms": round(_timed(lambda: deduplicate_company_titles(jobs)), 3),
        "bucketed_fuzzy_1000_ms": round(_timed(lambda: deduplicate_company_titles(jobs[:1000])), 3),
        "global_scan_fuzzy_1000_ms": round(_timed(lambda: _global_scan(jobs[:1000])), 3),
        "global_scan_fuzzy_4000_ms": round(_timed(lambda: _global_scan(jobs), 1), 3),
        "canonical_50k_ms": round(_timed(lambda: {canonicalize_url(url) for url in urls}), 3),
        "canonical_unique": len({canonicalize_url(url) for url in urls}),
        "startup_calls_for_DE_US_FR": fanout,
        **_feed_query_metrics(),
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
