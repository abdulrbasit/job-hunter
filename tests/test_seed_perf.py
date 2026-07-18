"""Phase 4/4 optimize — company store latency at 100k-row seed scale.

Seeds a fake 100k-row bundle (95k catalog + 5k review) through the real
ensure_seeded path, then times the queries the dashboard calls. Ceilings are
generous — this guards against an accidental O(n²) dedup or a dropped index,
not a tight benchmark. Run with -s to see the measured timings.
"""

from __future__ import annotations

import time
from pathlib import Path

from job_hunter.companies import store
from job_hunter.models import Company
from job_hunter.ux.web.api import DashAPI

_COUNTRIES = ("DE", "US", "GB", "FR", "NL")


def _fake_bundle(monkeypatch, n_main: int, n_review: int, version: str = "perf-v1") -> None:
    from job_hunter.companies import seed

    def main_rows():
        for i in range(n_main):
            yield Company(
                catalog_id=f"c{i}",
                name=f"Company {i}",
                career_url=f"https://c{i}.example/careers",
                country=_COUNTRIES[i % 5],
                city="geonames:2950159" if i % 10 == 0 else "",
                industry="software_it",
            )

    def review_rows():
        for i in range(n_review):
            yield {
                "id": f"r{i}",
                "name": f"Review {i}",
                "url": f"https://r{i}.example",
                "country": _COUNTRIES[i % 5],
                "industry": "",
                "reason": "industry_unmapped",
            }

    monkeypatch.setattr(
        seed, "manifest", lambda: {"files": {}, "review": {}, "total": n_main, "version": version}
    )
    monkeypatch.setattr(seed, "iter_seed_companies", main_rows)
    monkeypatch.setattr(seed, "iter_review_companies", review_rows)


def _timed(label: str, fn) -> float:  # noqa: ANN001 — test-local timing helper
    start = time.perf_counter()
    fn()
    elapsed = time.perf_counter() - start
    print(f"[perf] {label}: {elapsed * 1000:.1f}ms")  # noqa: T201 — intentional perf signal
    return elapsed


def test_store_stays_fast_at_100k_seed_rows(monkeypatch, tmp_path: Path) -> None:
    _fake_bundle(monkeypatch, 95_000, 5_000)
    api = DashAPI(tmp_path)

    assert _timed("ensure_seeded(100k)", lambda: store.ensure_seeded(tmp_path)) < 60.0
    assert store.company_count(tmp_path, source="catalog") == 100_000
    assert _timed("get_review_page(p2)", lambda: api.get_review_page(2)) < 2.0
    assert _timed("get_catalog_page(p3)", lambda: api.get_catalog_page(page=3)) < 2.0
    assert (
        _timed(
            "seed_progress",
            lambda: store.seed_progress(
                tmp_path, [{"country": "DE"}, {"country": "DE", "city": "geonames:2950159"}]
            ),
        )
        < 2.0
    )
    assert _timed("grow_catalog(no-op)", lambda: api.grow_catalog()) < 2.0

    # version bump re-seed exercises resolved-row preservation at scale — both scans are dict-based
    _fake_bundle(monkeypatch, 95_000, 5_000, version="perf-v2")
    assert _timed("re-seed(100k)", lambda: store.ensure_seeded(tmp_path)) < 60.0
