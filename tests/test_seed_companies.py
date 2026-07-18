"""Tests for the maintainer seeding pipeline: scripts/seed_companies.py + scripts/seed_providers/."""

from __future__ import annotations

import itertools
import json
from datetime import date
from pathlib import Path

from scripts import seed_companies
from scripts.seed_providers import iter_providers, manual_lists, wikidata


def test_provider_discovery_finds_bundled_providers() -> None:
    names = {provider.NAME for provider in iter_providers()}

    assert {"wikidata", "manual"} <= names


def test_rotation_buckets_are_disjoint_and_cover_every_country_weekly() -> None:
    from job_hunter.locations import countries

    buckets = [set(seed_companies.rotation_countries(date(2026, 7, 13 + offset))) for offset in range(7)]

    assert set().union(*buckets) == {c["code"] for c in countries()}
    for a, b in itertools.combinations(buckets, 2):
        assert not (a & b)


def test_seed_country_routes_complete_rows_to_shard_and_gapped_rows_to_review(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "DE.jsonl").write_text(
        '{"id":"sap","name":"SAP","url":"https://sap.com/careers","industry":"software_it"}\n', encoding="utf-8"
    )
    monkeypatch.setattr(seed_companies, "DATA_DIR", data_dir)
    fetched = [
        # keyword-mapped industry + canonical city + provenance
        {"name": "Deutsche Bahn", "url": "https://db.jobs/careers", "city": "Berlin", "industry_hint": "railway"},
        # alias-mapped industry
        {"name": "N27", "url": "https://n27.example/jobs", "industry_hint": "fintech"},
        # unmapped industry -> review
        {"name": "Mystery GmbH", "url": "https://mystery.example", "industry_hint": "zorbing"},
        # duplicate normalized name against existing shard -> skipped, original kept
        {"name": "SAP", "url": "https://sap.example/other", "industry_hint": "software"},
        # no url -> dropped entirely (not even review-worthy)
        {"name": "NoUrl AG", "url": ""},
        # non-https url -> review
        {"name": "HttpOnly", "url": "http://insecure.example", "industry_hint": "software"},
    ]
    monkeypatch.setattr(seed_companies, "_fetch_all", lambda country, city: [{**r, "_src": "test"} for r in fetched])

    result = seed_companies.seed_country("DE")

    shard = [json.loads(line) for line in (data_dir / "DE.jsonl").read_text(encoding="utf-8").splitlines()]
    by_name = {row["name"]: row for row in shard}
    assert by_name["Deutsche Bahn"]["industry"] == "transportation_logistics"
    assert by_name["Deutsche Bahn"]["city"].startswith("geonames:")
    assert by_name["Deutsche Bahn"]["src"] == "test"
    assert by_name["Deutsche Bahn"]["batch"]
    assert by_name["N27"]["industry"] == "finance"
    assert sum(1 for row in shard if row["name"] == "SAP") == 1
    assert by_name["SAP"]["url"] == "https://sap.com/careers"

    review = [json.loads(line) for line in (data_dir / "review" / "DE.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {row["name"] for row in review} == {"Mystery GmbH", "HttpOnly"}
    assert all(row["reason"] for row in review)

    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"]["DE"] == 3
    assert manifest["review"]["DE"] == 2
    assert result == {"fetched": 6, "accepted": 2, "review": 2}


def test_seed_country_with_city_keeps_only_rows_resolving_to_that_city(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(seed_companies, "DATA_DIR", data_dir)
    fetched = [
        {"name": "Muencher AG", "url": "https://muencher.example/jobs", "city": "Munich", "industry_hint": "software"},
        {"name": "Berliner AG", "url": "https://berliner.example/jobs", "city": "Berlin", "industry_hint": "software"},
        {"name": "Nowhere AG", "url": "https://nowhere.example/jobs", "industry_hint": "software"},
    ]
    monkeypatch.setattr(seed_companies, "_fetch_all", lambda country, city: [{**r, "_src": "test"} for r in fetched])

    seed_companies.seed_country("DE", city="Munich")

    shard = [json.loads(line) for line in (data_dir / "DE.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["name"] for row in shard] == ["Muencher AG"]


def test_reseeding_is_idempotent_and_review_rows_promoted_to_shard_leave_review(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(seed_companies, "DATA_DIR", data_dir)
    gapped = {"name": "Mystery GmbH", "url": "https://mystery.example", "industry_hint": "zorbing"}
    complete = {**gapped, "industry_hint": "software"}
    rows = [gapped]
    monkeypatch.setattr(seed_companies, "_fetch_all", lambda country, city: [{**r, "_src": "test"} for r in rows])

    seed_companies.seed_country("DE")
    seed_companies.seed_country("DE")
    review = (data_dir / "review" / "DE.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(review) == 1  # re-running does not duplicate review rows

    rows[:] = [complete]
    seed_companies.seed_country("DE")

    shard = [json.loads(line) for line in (data_dir / "DE.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["name"] for row in shard] == ["Mystery GmbH"]
    review = (data_dir / "review" / "DE.jsonl").read_text(encoding="utf-8").splitlines()
    assert review == []  # promoted out of the review queue


def test_wikidata_provider_parses_bindings_and_skips_unlabeled_entities(monkeypatch) -> None:
    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "results": {
                    "bindings": [
                        {
                            "companyLabel": {"value": "ACME"},
                            "website": {"value": "https://acme.de"},
                            "hqLabel": {"value": "Munich"},
                            "industryLabel": {"value": "software industry"},
                        },
                        {"companyLabel": {"value": "Q12345"}, "website": {"value": "https://anon.example"}},
                    ]
                }
            }

    captured: dict = {}

    def fake_get(url, params=None, headers=None, timeout=None):  # noqa: ANN001, ANN202
        captured["query"] = params["query"]
        captured["ua"] = headers["User-Agent"]
        return _Resp()

    monkeypatch.setattr(wikidata, "_sleep", lambda seconds: None)
    monkeypatch.setattr(wikidata.requests, "get", fake_get)

    rows = wikidata.fetch("DE")

    assert rows == [{"name": "ACME", "url": "https://acme.de", "city": "Munich", "industry_hint": "software industry"}]
    assert '"DE"' in captured["query"]
    assert "job-hunter" in captured["ua"]


def test_manual_lists_provider_reads_csv_drops_filtered_by_country(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(manual_lists, "DATA_DIR", tmp_path)
    (tmp_path / "employers.csv").write_text(
        "name,url,country,city,industry\n"
        "Siemens,https://siemens.com/careers,DE,Munich,manufacturing\n"
        "Nestle,https://nestle.com/jobs,CH,,other\n",
        encoding="utf-8",
    )

    rows = manual_lists.fetch("DE")

    assert len(rows) == 1
    assert rows[0]["name"] == "Siemens"
    assert rows[0]["city"] == "Munich"
    assert rows[0]["industry_hint"] == "manufacturing"
