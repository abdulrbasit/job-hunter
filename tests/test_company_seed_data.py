"""Tests for job_hunter/companies/seed.py and the bundled data/*.jsonl shards."""

from __future__ import annotations

from job_hunter.companies import seed
from job_hunter.config.reference_data import country_codes
from job_hunter.filters.catalog import load_filter_catalog


def test_manifest_matches_shard_row_counts() -> None:
    data = seed.manifest()
    counts: dict[str, int] = {}
    for catalog_id, name, url, country, industry in seed.iter_seed_rows():
        assert catalog_id and name and url and industry
        counts[country] = counts.get(country, 0) + 1

    assert counts == data["files"]
    assert sum(counts.values()) == data["total"]


def test_every_shard_country_is_a_known_iso_code() -> None:
    valid = country_codes()

    assert set(seed.manifest()["files"]) <= valid


def test_every_seed_row_has_a_known_industry() -> None:
    valid_industries = {industry.id for industry in load_filter_catalog().industries}

    for _catalog_id, _name, _url, _country, industry in seed.iter_seed_rows():
        assert industry in valid_industries


def test_every_seed_row_url_is_https() -> None:
    for _catalog_id, _name, url, _country, _industry in seed.iter_seed_rows():
        assert url.startswith("https://")


def test_seed_rows_unique_per_normalized_url_within_a_country() -> None:
    seen: dict[str, set[str]] = {}
    for _catalog_id, _name, url, country, _industry in seed.iter_seed_rows():
        normalized = url.strip().rstrip("/").lower()
        bucket = seen.setdefault(country, set())
        assert normalized not in bucket, f"duplicate {normalized!r} in {country}"
        bucket.add(normalized)
