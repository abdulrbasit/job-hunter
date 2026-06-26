from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import requests

from job_hunter.core.utils import title_matches
from job_hunter.models import JobPosting, ScrapeStats, SearchParams
from job_hunter.pipeline import enrichment, hunt
from job_hunter.sources import careerjet_source, himalayas_source, jobicy_source, orchestrator
from job_hunter.sources._policy import JobPolicy


def _posting(**overrides) -> JobPosting:
    values = {
        "title": "Product Manager",
        "company": "Acme",
        "url": "https://example.com/jobs/pm",
        "posted": datetime.now(UTC).date().isoformat(),
        "location": "Berlin",
        "snippet": "Own product discovery and delivery.",
        "source": "Test",
        "region": "berlin",
    }
    values.update(overrides)
    return JobPosting(**values)


def test_configured_title_exclusions_use_word_boundaries() -> None:
    assert title_matches("Staff Product Manager", ["Product Manager"], ["staff"]) is False
    assert title_matches("Staffing Product Manager", ["Product Manager"], ["staff"]) is True
    assert title_matches("VP, Product", ["Product"], ["vp"]) is False


def test_active_orchestrator_applies_policy_and_candidate_cache(monkeypatch) -> None:
    config = {
        "job_titles": ["Product Manager"],
        "exclusions": {
            "companies": ["Blocked Co"],
            "title_terms": ["staff"],
            "industries": [],
            "languages": [],
        },
        "regions": {
            "berlin": {
                "enabled": True,
                "country": "DE",
                "location": "Berlin",
                "search_lang": "en",
            }
        },
        "search": {},
    }

    class Source:
        source_name = "test"

        def fetch(self, _params):
            return [
                _posting(),
                _posting(title="Staff Product Manager", url="https://example.com/jobs/staff"),
                _posting(company="Blocked Co", url="https://example.com/jobs/blocked"),
                _posting(url="https://example.com/jobs/cached"),
            ]

    monkeypatch.setattr(orchestrator, "load_search_config", lambda: config)
    monkeypatch.setattr(orchestrator, "resolve_regions", lambda _cfg, _region: config["regions"])
    monkeypatch.setattr(orchestrator, "board_adapters", lambda: [Source()])
    monkeypatch.setattr(orchestrator, "probe_search_providers", lambda: set())
    monkeypatch.setattr(orchestrator, "load_cached_candidate_urls", lambda: {"https://example.com/jobs/cached"})

    jobs, stats = orchestrator.scrape_with_stats(depth="fast")

    assert [job.url for job in jobs] == ["https://example.com/jobs/pm"]
    assert stats.total_fetched == 4
    assert stats.total_after_policy == 1
    assert stats.rejected["excluded_title"] == 1
    assert stats.rejected["excluded_company"] == 1
    assert stats.rejected["cached_candidate"] == 1


def test_policy_rejects_invalid_future_and_stale_dates() -> None:
    policy = JobPolicy({"exclusions": {}})
    today = datetime.now(UTC)

    assert policy.rejection_reason(_posting(posted="not-a-date").to_dict(), ["Product Manager"]) == "invalid_date"
    assert (
        policy.rejection_reason(
            _posting(posted=(today + timedelta(days=3)).date().isoformat()).to_dict(),
            ["Product Manager"],
        )
        == "future_date"
    )
    assert (
        policy.rejection_reason(
            _posting(posted=(today - timedelta(days=46)).date().isoformat()).to_dict(),
            ["Product Manager"],
        )
        == "stale_date"
    )


def test_global_feed_is_fetched_once_for_all_regions(monkeypatch) -> None:
    config = {
        "job_titles": ["Product Manager"],
        "exclusions": {"companies": [], "title_terms": [], "industries": [], "languages": []},
        "regions": {
            "berlin": {"enabled": True, "country": "DE", "location": "Berlin"},
            "dublin": {"enabled": True, "country": "IE", "location": "Dublin"},
        },
        "search": {},
    }

    class GlobalSource:
        source_name = "global"
        global_feed = True
        calls = 0

        def fetch(self, _params):
            self.calls += 1
            return [_posting(location="Remote", region="")]

    source = GlobalSource()
    monkeypatch.setattr(orchestrator, "load_search_config", lambda: config)
    monkeypatch.setattr(orchestrator, "resolve_regions", lambda _cfg, _region: config["regions"])
    monkeypatch.setattr(orchestrator, "board_adapters", lambda: [source])
    monkeypatch.setattr(orchestrator, "probe_search_providers", lambda: set())
    monkeypatch.setattr(orchestrator, "load_cached_candidate_urls", lambda: set())

    jobs, _stats = orchestrator.scrape_with_stats(depth="fast")

    assert source.calls == 1
    assert jobs[0].region == "global_remote"


def test_specific_region_global_feed_uses_selected_region_params(monkeypatch) -> None:
    config = {
        "job_titles": ["Product Manager"],
        "exclusions": {"companies": [], "title_terms": [], "industries": [], "languages": []},
        "regions": {
            "berlin": {"enabled": True, "country": "DE", "location": "Berlin", "search_lang": "en"},
        },
        "search": {},
    }

    class GlobalSource:
        source_name = "global"
        global_feed = True

        def __init__(self):
            self.params = []

        def fetch(self, params):
            self.params.append(params)
            return [
                _posting(
                    location="Remote",
                    region=params.region_key,
                    location_restrictions=["Germany"],
                )
            ]

    source = GlobalSource()
    monkeypatch.setattr(orchestrator, "load_search_config", lambda: config)
    monkeypatch.setattr(orchestrator, "resolve_regions", lambda _cfg, _region: config["regions"])
    monkeypatch.setattr(orchestrator, "board_adapters", lambda: [source])
    monkeypatch.setattr(orchestrator, "probe_search_providers", lambda: set())
    monkeypatch.setattr(orchestrator, "load_cached_candidate_urls", lambda: set())

    jobs, _stats = orchestrator.scrape_with_stats(region="berlin", depth="fast")

    assert len(source.params) == 1
    assert source.params[0].region_key == "berlin"
    assert source.params[0].country == "DE"
    assert [job.region for job in jobs] == ["berlin"]


def test_enrichment_never_replaces_known_identity_with_unknown_values() -> None:
    job = _posting(source="Arbeitsagentur").to_dict()

    result = enrichment.enrich_snippets(
        [job],
        {"http": {"jd_enrichment": {"max_workers": 1, "skip_url_patterns": []}}},
        fetcher=lambda *_args, **_kwargs: {
            "title": "Unknown Role",
            "company": "Unknown Company",
            "source": "direct_link",
            "snippet": "A much longer job description.",
        },
    )[0]

    assert result["title"] == "Product Manager"
    assert result["company"] == "Acme"
    assert result["source"] == "Arbeitsagentur"
    assert result["enrichment_source"] == "direct_link"


def test_himalayas_accepts_seconds_and_milliseconds_timestamps() -> None:
    instant = datetime(2026, 6, 20, tzinfo=UTC)
    seconds = int(instant.timestamp())
    milliseconds = seconds * 1000

    assert himalayas_source._posted(seconds) == "2026-06-20"
    assert himalayas_source._posted(milliseconds) == "2026-06-20"


def test_jobicy_fetches_once_and_filters_all_titles(monkeypatch) -> None:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "jobs": [
            {
                "jobTitle": "Product Manager",
                "companyName": "Acme",
                "url": "https://example.com/jobs/pm",
                "pubDate": "2026-06-20T00:00:00Z",
                "jobGeo": "Germany",
                "jobDescription": "PM role",
            },
            {
                "jobTitle": "Product Owner",
                "companyName": "Other",
                "url": "https://example.com/jobs/po",
                "pubDate": "2026-06-20T00:00:00Z",
                "jobGeo": "Germany",
                "jobDescription": "PO role",
            },
        ]
    }
    get = MagicMock(return_value=response)
    monkeypatch.setattr(jobicy_source, "load_api_config", lambda: {"http": {"job_boards": {"jobicy": {}}}})
    monkeypatch.setattr(jobicy_source, "reserve_api_call", lambda _source: True)
    monkeypatch.setattr(jobicy_source.requests, "get", get)
    monkeypatch.setattr(jobicy_source, "_read_cache", lambda _geo: None)
    monkeypatch.setattr(jobicy_source, "_write_cache", lambda _geo, _jobs: None)

    jobs = jobicy_source.JobicySource().fetch(
        SearchParams(
            region_key="berlin",
            country="DE",
            location="Berlin",
            search_lang="en",
            job_titles=["Product Manager", "Product Owner"],
        )
    )

    assert len(jobs) == 2
    assert get.call_count == 1
    assert "tag" not in get.call_args.kwargs["params"]


def test_jobicy_uses_fresh_cache_without_network(monkeypatch) -> None:
    cached = [
        {
            "jobTitle": "Product Manager",
            "companyName": "Acme",
            "url": "https://example.com/jobs/pm",
            "pubDate": "2026-06-20T00:00:00Z",
            "jobGeo": "Germany",
            "jobDescription": "PM role",
        }
    ]
    get = MagicMock()
    monkeypatch.setattr(jobicy_source, "load_api_config", lambda: {"http": {"job_boards": {"jobicy": {}}}})
    monkeypatch.setattr(jobicy_source, "_read_cache", lambda _geo: cached)
    monkeypatch.setattr(jobicy_source.requests, "get", get)

    jobs = jobicy_source.JobicySource().fetch(
        SearchParams(
            region_key="berlin",
            country="DE",
            location="Berlin",
            search_lang="en",
            job_titles=["Product Manager"],
        )
    )

    assert len(jobs) == 1
    get.assert_not_called()


def test_careerjet_stops_after_terminal_http_error(monkeypatch) -> None:
    response = MagicMock()
    error = requests.HTTPError("429 Too Many Requests")
    error.response = MagicMock(status_code=429)
    response.raise_for_status.side_effect = error
    get = MagicMock(return_value=response)
    config = {"http": {"job_boards": {"careerjet": {"enabled": True, "affid": "test"}}}}
    monkeypatch.setattr(careerjet_source, "load_api_config", lambda: config)
    monkeypatch.setattr(careerjet_source.requests, "get", get)

    jobs = careerjet_source.CareerjetSource().fetch(
        SearchParams(
            region_key="berlin",
            country="DE",
            location="Berlin",
            search_lang="en",
            job_titles=["Product Manager", "Product Owner"],
        )
    )

    assert jobs == []
    assert get.call_count == 1


def test_snapshot_updates_candidate_cache_and_contains_run_metadata(monkeypatch, tmp_path) -> None:
    job = _posting().to_dict()
    stats = ScrapeStats(total_fetched=2, total_after_dedup=1, total_after_policy=1, duration_seconds=1.25)
    saved: list[set[str]] = []

    monkeypatch.setattr(hunt, "_jobs_from_hunt", lambda *_args, **_kwargs: ([job], set(), set(), stats))
    monkeypatch.setattr(hunt, "_drop_dead_urls", lambda jobs, *_args: jobs)
    monkeypatch.setattr(hunt, "_enrich", lambda jobs, _cfg: jobs)
    monkeypatch.setattr(hunt, "load_cached_candidate_urls", lambda: {"https://example.com/jobs/old"})
    monkeypatch.setattr(hunt, "save_cached_candidate_urls", lambda urls: saved.append(urls))

    path, count, returned_stats = hunt.run_hunt_scrape_only("berlin", tmp_path, api_cfg={})
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert count == 1
    assert returned_stats == stats
    assert "T" in payload["created_at"]
    assert payload["stats"]["total_after_policy"] == 1
    assert path.name.startswith("2026-")
    assert path.name.endswith("_berlin_candidates.json")
    assert saved == [{"https://example.com/jobs/old", "https://example.com/jobs/pm"}]
