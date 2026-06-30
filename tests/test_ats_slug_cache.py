"""Tests for ats_slugs and ats_apis."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from job_hunter.models import JobPosting
from job_hunter.sources.ats_apis import fetch_platform_jobs
from job_hunter.sources.ats_slugs import harvest_slugs, load_slug_store, query_ats_by_slugs, update_slug_store

# ---------------------------------------------------------------------------
# harvest_slugs
# ---------------------------------------------------------------------------


def _jp(url: str) -> JobPosting:
    return JobPosting(title="Engineer", company="Acme", url=url)


class TestHarvestSlugs:
    def test_extracts_greenhouse_slug(self) -> None:
        jobs = [_jp("https://boards.greenhouse.io/stripe/jobs/12345")]
        assert harvest_slugs(jobs) == {"greenhouse": {"stripe"}}

    def test_extracts_lever_slug(self) -> None:
        jobs = [_jp("https://jobs.lever.co/getyourguide/abc-123")]
        assert harvest_slugs(jobs) == {"lever": {"getyourguide"}}

    def test_extracts_ashby_slug(self) -> None:
        jobs = [_jp("https://jobs.ashbyhq.com/linear/uuid-1")]
        assert harvest_slugs(jobs) == {"ashby": {"linear"}}

    def test_ignores_non_ats_urls(self) -> None:
        jobs = [_jp("https://www.example.com/jobs/123")]
        assert harvest_slugs(jobs) == {}

    def test_accepts_dict_jobs(self) -> None:
        jobs = [{"url": "https://boards.greenhouse.io/acme/jobs/1"}]
        assert harvest_slugs(jobs) == {"greenhouse": {"acme"}}

    def test_deduplicates_slugs(self) -> None:
        jobs = [
            _jp("https://jobs.lever.co/getyourguide/abc"),
            _jp("https://jobs.lever.co/getyourguide/xyz"),
        ]
        result = harvest_slugs(jobs)
        assert result == {"lever": {"getyourguide"}}

    def test_accumulates_multiple_platforms(self) -> None:
        jobs = [
            _jp("https://boards.greenhouse.io/stripe/jobs/1"),
            _jp("https://jobs.lever.co/getyourguide/abc"),
        ]
        result = harvest_slugs(jobs)
        assert result == {"greenhouse": {"stripe"}, "lever": {"getyourguide"}}

    def test_empty_input(self) -> None:
        assert harvest_slugs([]) == {}


# ---------------------------------------------------------------------------
# load_slug_store / update_slug_store
# ---------------------------------------------------------------------------


class TestSlugStore:
    def test_load_returns_empty_when_missing(self, tmp_path: Path) -> None:
        assert load_slug_store(tmp_path) == {}

    def test_roundtrip(self, tmp_path: Path) -> None:
        update_slug_store(tmp_path, {"greenhouse": {"stripe", "acme"}})
        store = load_slug_store(tmp_path)
        assert set(store["greenhouse"]) == {"stripe", "acme"}

    def test_merge_deduplicates(self, tmp_path: Path) -> None:
        update_slug_store(tmp_path, {"lever": {"getyourguide"}})
        update_slug_store(tmp_path, {"lever": {"getyourguide", "soundcloud"}})
        store = load_slug_store(tmp_path)
        assert set(store["lever"]) == {"getyourguide", "soundcloud"}

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        workspace = tmp_path / "nested"
        update_slug_store(workspace, {"greenhouse": {"acme"}})
        assert (workspace / "outputs/state/ats_slugs.yml").exists()

    def test_no_write_on_empty(self, tmp_path: Path) -> None:
        update_slug_store(tmp_path, {})
        assert not (tmp_path / "outputs/state/ats_slugs.yml").exists()


# ---------------------------------------------------------------------------
# fetch_platform_jobs
# ---------------------------------------------------------------------------


class TestFetchPlatformJobs:
    def test_unknown_platform_returns_empty(self) -> None:
        assert fetch_platform_jobs("unknown_ats", "acme", 5) == []

    def test_greenhouse_parses_response(self) -> None:
        mock_data = {
            "jobs": [
                {
                    "title": "Product Manager",
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                    "location": {"name": "Berlin"},
                }
            ]
        }
        with patch("job_hunter.sources.ats_apis._get_json", return_value=mock_data):
            jobs = fetch_platform_jobs("greenhouse", "acme", 5)
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Product Manager"
        assert jobs[0]["url"] == "https://boards.greenhouse.io/acme/jobs/1"
        assert jobs[0]["location"] == "Berlin"

    def test_lever_parses_response(self) -> None:
        mock_data = [
            {
                "text": "Senior Engineer",
                "hostedUrl": "https://jobs.lever.co/acme/abc",
                "categories": {"location": "Berlin, Germany"},
                "descriptionPlain": "Full job text here.",
            }
        ]
        with patch("job_hunter.sources.ats_apis._get_json", return_value=mock_data):
            jobs = fetch_platform_jobs("lever", "acme", 5)
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Senior Engineer"
        assert jobs[0]["location"] == "Berlin, Germany"

    def test_returns_empty_on_http_error(self) -> None:
        with patch("job_hunter.sources.ats_apis._get_json", return_value=None):
            assert fetch_platform_jobs("greenhouse", "acme", 5) == []

    def test_skips_jobs_missing_url_or_title(self) -> None:
        mock_data = {"jobs": [{"title": "", "absolute_url": "https://example.com", "location": {"name": ""}}]}
        with patch("job_hunter.sources.ats_apis._get_json", return_value=mock_data):
            assert fetch_platform_jobs("greenhouse", "acme", 5) == []


# ---------------------------------------------------------------------------
# query_ats_by_slugs
# ---------------------------------------------------------------------------


class TestQueryAtsBySlugs:
    _regions = {"primary": {"location": "Berlin"}}
    _titles = ["Product Manager"]
    _excluded = []

    def test_returns_empty_on_empty_store(self) -> None:
        assert query_ats_by_slugs({}, self._titles, self._regions, self._excluded) == []

    def test_filters_by_title(self) -> None:
        mock_jobs = [
            {"title": "Product Manager", "url": "https://jobs.lever.co/acme/1", "location": "Berlin", "snippet": ""},
            {"title": "Data Scientist", "url": "https://jobs.lever.co/acme/2", "location": "Berlin", "snippet": ""},
        ]
        with patch("job_hunter.sources.ats_apis.fetch_platform_jobs", return_value=mock_jobs):
            results = query_ats_by_slugs({"lever": ["acme"]}, self._titles, self._regions, self._excluded)
        assert len(results) == 1
        assert results[0]["title"] == "Product Manager"

    def test_location_filter_skips_mismatched(self) -> None:
        mock_jobs = [
            {"title": "Product Manager", "url": "https://jobs.lever.co/acme/1", "location": "New York", "snippet": ""},
        ]
        with patch("job_hunter.sources.ats_apis.fetch_platform_jobs", return_value=mock_jobs):
            results = query_ats_by_slugs({"lever": ["acme"]}, self._titles, self._regions, self._excluded)
        assert results == []

    def test_no_location_in_job_passes_through(self) -> None:
        mock_jobs = [
            {"title": "Product Manager", "url": "https://jobs.lever.co/acme/1", "location": "", "snippet": ""},
        ]
        with patch("job_hunter.sources.ats_apis.fetch_platform_jobs", return_value=mock_jobs):
            results = query_ats_by_slugs({"lever": ["acme"]}, self._titles, self._regions, self._excluded)
        assert len(results) == 1

    def test_deduplicates_urls(self) -> None:
        mock_jobs = [
            {"title": "Product Manager", "url": "https://jobs.lever.co/acme/1", "location": "", "snippet": ""},
        ]
        with patch("job_hunter.sources.ats_apis.fetch_platform_jobs", return_value=mock_jobs):
            results = query_ats_by_slugs({"lever": ["acme", "acme"]}, self._titles, self._regions, self._excluded)
        assert len(results) == 1

    def test_source_field_set_to_platform(self) -> None:
        mock_jobs = [
            {
                "title": "Product Manager",
                "url": "https://boards.greenhouse.io/acme/jobs/1",
                "location": "",
                "snippet": "",
            },
        ]
        with patch("job_hunter.sources.ats_apis.fetch_platform_jobs", return_value=mock_jobs):
            results = query_ats_by_slugs({"greenhouse": ["acme"]}, self._titles, self._regions, self._excluded)
        assert results[0]["source"] == "ats_slug/greenhouse"
