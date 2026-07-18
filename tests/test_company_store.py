"""Tests for job_hunter/companies/store.py — the SQLite-backed company store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from job_hunter.companies import store


def _targets(*entries: dict) -> list[dict]:
    return list(entries)


def test_sync_user_targets_inserts_rows(tmp_path: Path) -> None:
    store.sync_user_targets(
        tmp_path, _targets({"name": "Acme", "url": "https://acme.example/careers", "country": "DE"})
    )

    page = store.query_page(tmp_path, source="user")

    assert page["total"] == 1
    assert page["items"][0]["name"] == "Acme"
    assert page["items"][0]["industry"] == "other"
    assert page["items"][0]["enabled"] == 1


def test_sync_user_targets_replaces_all_user_rows(tmp_path: Path) -> None:
    store.sync_user_targets(
        tmp_path, _targets({"name": "Acme", "url": "https://acme.example/careers", "country": "DE"})
    )

    store.sync_user_targets(
        tmp_path, _targets({"name": "Beta", "url": "https://beta.example/careers", "country": "FR", "enabled": False})
    )

    page = store.query_page(tmp_path, source="user")
    assert page["total"] == 1
    assert page["items"][0]["name"] == "Beta"
    assert page["items"][0]["enabled"] == 0


def test_sync_user_targets_resolves_known_city_to_canonical_id(tmp_path: Path) -> None:
    store.sync_user_targets(
        tmp_path, _targets({"name": "Acme", "url": "https://acme.example/careers", "country": "DE", "city": "Berlin"})
    )

    row = store.query_page(tmp_path, source="user")["items"][0]

    assert row["city"] and row["city"].startswith("geonames:")


def test_sync_user_targets_drops_unresolvable_city_to_null(tmp_path: Path) -> None:
    store.sync_user_targets(
        tmp_path,
        _targets({"name": "Acme", "url": "https://acme.example/careers", "country": "DE", "city": "Nowhereville"}),
    )

    row = store.query_page(tmp_path, source="user")["items"][0]

    assert row["city"] is None


def test_query_page_filters_by_country_industry_and_enabled(tmp_path: Path) -> None:
    store.sync_user_targets(
        tmp_path,
        _targets(
            {"name": "Acme DE", "url": "https://acme.example/de", "country": "DE", "industry": "software_it"},
            {
                "name": "Acme FR",
                "url": "https://acme.example/fr",
                "country": "FR",
                "industry": "finance",
                "enabled": False,
            },
        ),
    )

    assert [r["name"] for r in store.query_page(tmp_path, country="DE")["items"]] == ["Acme DE"]
    assert [r["name"] for r in store.query_page(tmp_path, enabled=False)["items"]] == ["Acme FR"]
    assert store.query_page(tmp_path, industry="software_it")["total"] == 1


def test_query_page_search_matches_name(tmp_path: Path) -> None:
    store.sync_user_targets(
        tmp_path,
        _targets(
            {"name": "Acme Corp", "url": "https://acme.example/careers", "country": "DE"},
            {"name": "Other Co", "url": "https://other.example/careers", "country": "DE"},
        ),
    )

    result = store.query_page(tmp_path, search="acme")

    assert [r["name"] for r in result["items"]] == ["Acme Corp"]


def test_query_page_paginates(tmp_path: Path) -> None:
    store.sync_user_targets(
        tmp_path,
        _targets(*[{"name": f"Co{i}", "url": f"https://co{i}.example/careers", "country": "DE"} for i in range(5)]),
    )

    page1 = store.query_page(tmp_path, page=1, page_size=2)
    page3 = store.query_page(tmp_path, page=3, page_size=2)

    assert page1["total"] == 5
    assert page1["pages"] == 3
    assert len(page1["items"]) == 2
    assert len(page3["items"]) == 1


def test_candidate_companies_gates_by_country(tmp_path: Path) -> None:
    store.sync_user_targets(
        tmp_path,
        _targets(
            {"name": "Acme DE", "url": "https://acme.example/de", "country": "DE"},
            {"name": "Acme US", "url": "https://acme.example/us", "country": "US"},
        ),
    )

    result = store.candidate_companies(tmp_path, countries=["DE"])

    assert [r["name"] for r in result] == ["Acme DE"]


def test_candidate_companies_none_countries_matches_every_country(tmp_path: Path) -> None:
    store.sync_user_targets(
        tmp_path,
        _targets(
            {"name": "Acme DE", "url": "https://acme.example/de", "country": "DE"},
            {"name": "Acme US", "url": "https://acme.example/us", "country": "US"},
        ),
    )

    result = store.candidate_companies(tmp_path, countries=None)

    assert {r["name"] for r in result} == {"Acme DE", "Acme US"}


def test_candidate_companies_empty_countries_list_matches_nothing(tmp_path: Path) -> None:
    store.sync_user_targets(tmp_path, _targets({"name": "Acme DE", "url": "https://acme.example/de", "country": "DE"}))

    assert store.candidate_companies(tmp_path, countries=[]) == []


def test_candidate_companies_excludes_disabled(tmp_path: Path) -> None:
    store.sync_user_targets(
        tmp_path, _targets({"name": "Acme DE", "url": "https://acme.example/de", "country": "DE", "enabled": False})
    )

    assert store.candidate_companies(tmp_path, countries=["DE"]) == []


def test_candidate_companies_excludes_by_industry(tmp_path: Path) -> None:
    store.sync_user_targets(
        tmp_path,
        _targets({"name": "Acme DE", "url": "https://acme.example/de", "country": "DE", "industry": "software_it"}),
    )

    assert store.candidate_companies(tmp_path, countries=["DE"], excluded_industries=["software_it"]) == []
    assert len(store.candidate_companies(tmp_path, countries=["DE"], excluded_industries=["finance"])) == 1


def test_set_enabled_updates_selected_ids(tmp_path: Path) -> None:
    store.sync_user_targets(
        tmp_path, _targets({"name": "Acme", "url": "https://acme.example/careers", "country": "DE", "enabled": False})
    )
    row = store.query_page(tmp_path)["items"][0]

    n = store.set_enabled(tmp_path, [row["id"]], True)

    assert n == 1
    assert store.query_page(tmp_path)["items"][0]["enabled"] == 1


def test_set_enabled_where_matches_filter_only(tmp_path: Path) -> None:
    store.sync_user_targets(
        tmp_path,
        _targets(
            {"name": "Acme DE", "url": "https://acme.example/de", "country": "DE", "enabled": False},
            {"name": "Acme FR", "url": "https://acme.example/fr", "country": "FR", "enabled": False},
        ),
    )

    n = store.set_enabled_where(tmp_path, country="DE", new_enabled=True)

    assert n == 1
    assert store.query_page(tmp_path, country="DE")["items"][0]["enabled"] == 1
    assert store.query_page(tmp_path, country="FR")["items"][0]["enabled"] == 0


def test_company_count_and_distinct_countries(tmp_path: Path) -> None:
    store.sync_user_targets(
        tmp_path,
        _targets(
            {"name": "Acme DE", "url": "https://acme.example/de", "country": "DE"},
            {"name": "Acme FR", "url": "https://acme.example/fr", "country": "FR", "enabled": False},
        ),
    )

    assert store.company_count(tmp_path) == 2
    assert store.company_count(tmp_path, enabled=True) == 1
    assert store.distinct_countries(tmp_path) == ["DE", "FR"]


def test_industry_counts(tmp_path: Path) -> None:
    store.sync_user_targets(
        tmp_path,
        _targets(
            {"name": "A", "url": "https://a.example/careers", "country": "DE", "industry": "software_it"},
            {"name": "B", "url": "https://b.example/careers", "country": "DE", "industry": "software_it"},
            {"name": "C", "url": "https://c.example/careers", "country": "DE", "industry": "finance"},
        ),
    )

    counts = {row["industry"]: row["count"] for row in store.industry_counts(tmp_path, source="user")}

    assert counts == {"software_it": 2, "finance": 1}


def test_ensure_seeded_imports_bundled_catalog(tmp_path: Path) -> None:
    seeded = store.ensure_seeded(tmp_path)

    assert seeded is True
    assert store.company_count(tmp_path, source="catalog") > 1000
    assert store.ensure_seeded(tmp_path) is False  # same seed version — no-op


def test_ensure_seeded_reseed_preserves_enabled_flags_and_user_rows(tmp_path: Path) -> None:
    store.ensure_seeded(tmp_path)
    target = store.query_page(tmp_path, source="catalog", page_size=1)["items"][0]
    store.set_enabled(tmp_path, [target["id"]], True)
    store.sync_user_targets(
        tmp_path, _targets({"name": "My Own Co", "url": "https://my-own-co.example/careers", "country": "US"})
    )

    with sqlite3.connect(store.db_path(tmp_path)) as conn:
        conn.execute("UPDATE companies_meta SET value = 'stale-version' WHERE key = 'seed_version'")
        conn.commit()

    assert store.ensure_seeded(tmp_path) is True

    reseeded = store.query_page(tmp_path, source="catalog", search=target["name"], country=target["country"])["items"]
    assert reseeded and reseeded[0]["enabled"] == 1
    user_rows = store.query_page(tmp_path, source="user")["items"]
    assert any(r["name"] == "My Own Co" for r in user_rows)


def test_candidate_companies_prefers_user_row_over_catalog_row_with_same_url(tmp_path: Path) -> None:
    store.ensure_seeded(tmp_path)
    catalog_row = store.query_page(tmp_path, source="catalog", page_size=1)["items"][0]
    store.set_enabled(tmp_path, [catalog_row["id"]], True)
    store.sync_user_targets(
        tmp_path, _targets({"name": "Override Name", "url": catalog_row["url"], "country": catalog_row["country"]})
    )

    result = store.candidate_companies(tmp_path, countries=[catalog_row["country"]])

    matches = [r for r in result if r["normalized_url"] == catalog_row["normalized_url"]]
    assert len(matches) == 1
    assert matches[0]["source"] == "user"
    assert matches[0]["name"] == "Override Name"


def test_set_enabled_by_catalog_ids(tmp_path: Path) -> None:
    store.ensure_seeded(tmp_path)
    row = store.query_page(tmp_path, source="catalog", page_size=1)["items"][0]

    n = store.set_enabled_by_catalog_ids(tmp_path, [row["catalog_id"]], True)

    assert n >= 1
    assert store.get_by_id(tmp_path, row["id"])["enabled"] == 1


def _fake_seed(monkeypatch, main_rows: list[dict], review_rows: list[dict], version: str = "v-test") -> None:
    from job_hunter.companies import seed
    from job_hunter.models import Company

    monkeypatch.setattr(
        seed, "manifest", lambda: {"files": {}, "review": {}, "total": len(main_rows), "version": version}
    )
    monkeypatch.setattr(seed, "iter_seed_companies", lambda: iter([Company(**row) for row in main_rows]))
    monkeypatch.setattr(seed, "iter_review_companies", lambda: iter(list(review_rows)))


_MAIN = {
    "name": "Good Co",
    "career_url": "https://good.example/careers",
    "country": "DE",
    "industry": "software_it",
    "city": "geonames:2950159",
    "catalog_id": "good_co",
}
_REVIEW = {
    "id": "gap_co",
    "name": "Gap Co",
    "url": "https://gap.example",
    "country": "DE",
    "industry": "",
    "reason": "industry_unmapped",
}


def test_ensure_seeded_imports_review_rows_flagged_and_disabled(monkeypatch, tmp_path: Path) -> None:
    _fake_seed(monkeypatch, [_MAIN], [_REVIEW])

    assert store.ensure_seeded(tmp_path) is True

    good = store.query_page(tmp_path, search="Good Co")["items"][0]
    assert good["needs_review"] == 0
    assert good["city"] == "geonames:2950159"  # catalog rows now carry their bundled city
    gap = store.query_page(tmp_path, needs_review=True)["items"][0]
    assert gap["name"] == "Gap Co"
    assert gap["enabled"] == 0
    assert gap["review_reason"] == "industry_unmapped"
    assert store.company_count(tmp_path, needs_review=True) == 1
    # review rows never enter the huntable pool
    assert store.candidate_companies(tmp_path, countries=None) == []


def test_resolve_review_validates_fixes_and_clears_flag(monkeypatch, tmp_path: Path) -> None:
    _fake_seed(monkeypatch, [], [_REVIEW])
    store.ensure_seeded(tmp_path)
    row = store.query_page(tmp_path, needs_review=True)["items"][0]

    bad = store.resolve_review(tmp_path, row["id"], industry="not_a_real_industry")
    assert bad["ok"] is False and bad["errors"]

    good = store.resolve_review(tmp_path, row["id"], industry="software_it")
    assert good == {"ok": True, "errors": []}
    fixed = store.get_by_id(tmp_path, row["id"])
    assert fixed["needs_review"] == 0
    assert fixed["industry"] == "software_it"
    assert store.company_count(tmp_path, needs_review=True) == 0


def test_reseed_preserves_resolved_review_rows(monkeypatch, tmp_path: Path) -> None:
    _fake_seed(monkeypatch, [], [_REVIEW], version="v1")
    store.ensure_seeded(tmp_path)
    row = store.query_page(tmp_path, needs_review=True)["items"][0]
    store.resolve_review(tmp_path, row["id"], industry="software_it")
    store.set_enabled(tmp_path, [row["id"]], True)

    _fake_seed(monkeypatch, [], [_REVIEW], version="v2")
    assert store.ensure_seeded(tmp_path) is True

    kept = store.query_page(tmp_path, search="Gap Co")["items"][0]
    assert kept["needs_review"] == 0
    assert kept["industry"] == "software_it"
    assert kept["enabled"] == 1


def test_seed_progress_counts_catalog_rows_per_target(monkeypatch, tmp_path: Path) -> None:
    other_city = {**_MAIN, "name": "Elsewhere Co", "career_url": "https://elsewhere.example", "city": ""}
    _fake_seed(monkeypatch, [_MAIN, other_city], [_REVIEW])
    store.ensure_seeded(tmp_path)

    progress = store.seed_progress(tmp_path, [{"country": "DE"}, {"country": "DE", "city": "geonames:2950159"}])

    assert progress == [
        {"country": "DE", "city": "", "count": 2, "target": 1000},
        {"country": "DE", "city": "geonames:2950159", "count": 1, "target": 1000},
    ]
