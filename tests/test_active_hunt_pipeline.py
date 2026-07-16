from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import requests

from job_hunter.core.utils import title_matches
from job_hunter.models import JobPosting, ScrapeStats, SearchParams
from job_hunter.pipeline import enrichment, hunt
from job_hunter.sources import orchestrator
from job_hunter.sources.boards import careerjet as careerjet_source
from job_hunter.sources.boards import himalayas as himalayas_source
from job_hunter.sources.boards import jobicy as jobicy_source
from job_hunter.sources.policy import JobPolicy
from job_hunter.sources.search import ats_discovery as _ats_mod


def _posting(**overrides) -> JobPosting:
    values = {
        "title": "Product Manager",
        "company": "Acme",
        "url": "https://example.com/jobs/pm",
        "posted_date_text": datetime.now(UTC).date().isoformat(),
        "location": "Berlin",
        "snippet": "Own product discovery and delivery.",
        "source": "Test",
        "region": "berlin",
    }
    values.update(overrides)
    return JobPosting(**values)


def test_new_candidate_dicts_converts_models_and_deduplicates_urls() -> None:
    seen = {"https://example.com/jobs/seen"}
    postings = [
        _posting(url="https://example.com/jobs/new"),
        _posting(url="https://example.com/jobs/new"),
        _posting(url="https://example.com/jobs/seen"),
        _posting(url=""),
    ]

    candidates = hunt._new_candidate_dicts(postings, seen)

    assert [job["url"] for job in candidates] == ["https://example.com/jobs/new"]
    assert seen == {"https://example.com/jobs/seen", "https://example.com/jobs/new"}


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
    monkeypatch.setattr(orchestrator, "resolve_regions", lambda _config, _region: config["regions"])
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

    assert (
        policy.rejection_reason(_posting(posted_date_text="not-a-date").model_dump(), ["Product Manager"])
        == "invalid_date"
    )
    assert (
        policy.rejection_reason(
            _posting(posted_date_text=(today + timedelta(days=3)).date().isoformat()).model_dump(),
            ["Product Manager"],
        )
        == "future_date"
    )
    assert (
        policy.rejection_reason(
            _posting(posted_date_text=(today - timedelta(days=46)).date().isoformat()).model_dump(),
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
    monkeypatch.setattr(orchestrator, "resolve_regions", lambda _config, _region: config["regions"])
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
    monkeypatch.setattr(orchestrator, "resolve_regions", lambda _config, _region: config["regions"])
    monkeypatch.setattr(orchestrator, "board_adapters", lambda: [source])
    monkeypatch.setattr(orchestrator, "probe_search_providers", lambda: set())
    monkeypatch.setattr(orchestrator, "load_cached_candidate_urls", lambda: set())

    jobs, _stats = orchestrator.scrape_with_stats(region="berlin", depth="fast")

    assert len(source.params) == 1
    assert source.params[0].region_key == "berlin"
    assert source.params[0].country == "DE"
    assert [job.region for job in jobs] == ["berlin"]


def test_ats_discovery_jobs_counted_under_source_region_not_unknown(monkeypatch) -> None:
    """ATS-discovered jobs must carry region="berlin" so stats attribute them to
    the region that was actually searched, not the "unknown" fallback bucket
    (task: _process_ats_result must set "region" on every appended job dict)."""
    config = {
        "job_titles": ["Product Manager"],
        "exclusions": {"companies": [], "title_terms": [], "industries": [], "languages": []},
        "regions": {
            "berlin": {"enabled": True, "country": "DE", "location": "Berlin", "search_lang": "en"},
        },
        "search": {},
    }

    monkeypatch.setattr(orchestrator, "load_search_config", lambda: config)
    monkeypatch.setattr(orchestrator, "resolve_regions", lambda _config, _region: config["regions"])
    monkeypatch.setattr(orchestrator, "probe_search_providers", lambda: set())
    monkeypatch.setattr(orchestrator, "load_cached_candidate_urls", lambda: set())
    monkeypatch.setattr(
        _ats_mod,
        "discover_ats_jobs_by_search",
        lambda *_a, **_k: [
            {
                "title": "Product Manager",
                "company": "Acme",
                "url": "https://jobs.lever.co/acme/33333333-3333-3333-3333-333333333333",
                "location": "Berlin",
                "source": "SearXNG ATS discovery: lever",
                "region": "berlin",
            }
        ],
    )

    jobs, stats = orchestrator.scrape_with_stats(
        depth="standard", include_boards=False, include_ats_slug=False, include_ats_discovery=True
    )

    assert len(jobs) == 1
    assert jobs[0].region == "berlin"
    assert "unknown" not in stats.accepted_by_region
    assert stats.accepted_by_region.get("berlin") == 1


def test_deep_depth_passes_larger_max_results_than_standard() -> None:
    """_params_for_region only raises max_results for depth='deep' — the
    adaptive/deep-attempt signal paged adapters use to fetch more pages."""
    from job_hunter.constants import DEFAULT_BACKFILL_MAX_RESULTS, DEFAULT_STANDARD_MAX_RESULTS

    region_config = {"country": "DE", "location": "Berlin", "search_lang": "en"}

    assert orchestrator._max_results_for_depth("standard") == DEFAULT_STANDARD_MAX_RESULTS
    assert orchestrator._max_results_for_depth("fast") == DEFAULT_STANDARD_MAX_RESULTS
    assert orchestrator._max_results_for_depth("deep") == DEFAULT_BACKFILL_MAX_RESULTS

    standard_params = orchestrator._params_for_region(
        "berlin", region_config, ["Product Manager"], [], max_results=orchestrator._max_results_for_depth("standard")
    )
    deep_params = orchestrator._params_for_region(
        "berlin", region_config, ["Product Manager"], [], max_results=orchestrator._max_results_for_depth("deep")
    )
    assert standard_params.max_results == DEFAULT_STANDARD_MAX_RESULTS
    assert deep_params.max_results == DEFAULT_BACKFILL_MAX_RESULTS
    assert deep_params.max_results > standard_params.max_results


def test_enrichment_never_replaces_known_identity_with_unknown_values() -> None:
    job = _posting(source="Arbeitsagentur").model_dump()

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
    monkeypatch.setattr(jobicy_source, "get_api_config", lambda: {"http": {"job_boards": {"jobicy": {}}}})
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
    monkeypatch.setattr(jobicy_source, "get_api_config", lambda: {"http": {"job_boards": {"jobicy": {}}}})
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
    monkeypatch.setattr(careerjet_source, "get_api_config", lambda: config)
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
    """run_hunt_scrape_only routes through the adaptive per-region hunt, so mock
    _adaptive_region_hunt (the per-region unit) rather than a one-shot scrape."""
    from job_hunter.tracking.repository import get_discovered_jobs

    job = _posting().model_dump()
    saved: list[set[str]] = []

    monkeypatch.setattr(hunt, "load_search_config", lambda: {})
    monkeypatch.setattr(hunt, "enabled_regions", lambda _config, _region: {"berlin": {}})
    monkeypatch.setattr(hunt, "_adaptive_region_hunt", lambda *_a, **_k: [job])
    monkeypatch.setattr(hunt, "load_cached_candidate_urls", lambda: {"https://example.com/jobs/old"})
    monkeypatch.setattr(hunt, "save_cached_candidate_urls", lambda urls: saved.append(urls))

    run_id, count, returned_stats = hunt.run_hunt_scrape_only("berlin", tmp_path, api_config={})

    assert count == 1
    assert isinstance(returned_stats, ScrapeStats)
    assert isinstance(run_id, str) and "T" in run_id
    assert saved == [{"https://example.com/jobs/old", "https://example.com/jobs/pm"}]
    db_jobs = get_discovered_jobs(tmp_path, run_id=run_id)
    assert len(db_jobs) == 1


# ── Adaptive per-region hunt ─────────────────────────────────────────────────


def _fake_postings(n: int, prefix: str) -> list[JobPosting]:
    return [_posting(url=f"https://example.com/{prefix}/{i}", company=f"Co{prefix}{i}", region="") for i in range(n)]


def _pass_through_quality_pipeline(monkeypatch) -> None:
    """Make every stage between passes a no-op pass-through so a test controls
    quality count purely via how many postings scrape_with_stats returns."""
    monkeypatch.setattr(hunt, "filter_new_jobs", lambda jobs, **_k: (jobs, set()))
    monkeypatch.setattr(hunt, "_drop_dead_urls", lambda jobs, *_a, **_k: jobs)
    monkeypatch.setattr(hunt, "apply_pre_enrichment_quality_gate", lambda jobs, _cfg: (jobs, []))
    monkeypatch.setattr(hunt, "_enrich", lambda jobs, _cfg: jobs)
    monkeypatch.setattr(hunt, "screen_jobs_by_rules", lambda jobs, _cfg: (jobs, []))


def _scrape_stub(standard=0, deep=0, ats_slug=0, ats_discovery=0):
    """Fake scrape_with_stats that returns a fixed candidate count per pass,
    identified by the same kwargs _ADAPTIVE_PASSES uses to distinguish them."""

    def fake(region=None, *, depth="standard", include_boards=True, include_ats_slug=True, include_ats_discovery=True):
        if include_boards and depth == "fast":
            return _fake_postings(standard, "standard"), ScrapeStats()
        if include_boards and depth == "deep":
            return _fake_postings(deep, "deep"), ScrapeStats()
        if not include_boards and not include_ats_discovery:
            return _fake_postings(ats_slug, "atsslug"), ScrapeStats()
        if not include_boards and not include_ats_slug:
            return _fake_postings(ats_discovery, "atsdiscovery"), ScrapeStats()
        return [], ScrapeStats()

    return fake


def test_adaptive_region_meets_target_in_standard_pass(monkeypatch) -> None:
    calls = []
    stub = _scrape_stub(standard=5, deep=5, ats_slug=5, ats_discovery=5)

    def tracking_stub(region=None, **kwargs):
        calls.append(kwargs.get("depth"))
        return stub(region=region, **kwargs)

    monkeypatch.setattr(hunt, "scrape_with_stats", tracking_stub)
    _pass_through_quality_pipeline(monkeypatch)

    jobs = hunt._adaptive_region_hunt("bh", {}, {}, MagicMock(), 5, ScrapeStats())

    assert len(jobs) == 5
    assert calls == ["fast"]  # only the standard pass ran


def test_adaptive_region_reaches_target_only_after_deep_pass(monkeypatch) -> None:
    calls = []
    stub = _scrape_stub(standard=2, deep=10, ats_slug=10, ats_discovery=10)

    def tracking_stub(region=None, **kwargs):
        calls.append(kwargs.get("depth"))
        return stub(region=region, **kwargs)

    monkeypatch.setattr(hunt, "scrape_with_stats", tracking_stub)
    _pass_through_quality_pipeline(monkeypatch)

    jobs = hunt._adaptive_region_hunt("bh", {}, {}, MagicMock(), 5, ScrapeStats())

    assert len(jobs) == 12  # 2 (standard) + 10 (deep)
    assert calls == ["fast", "deep"]


def test_adaptive_region_reaches_target_only_after_ats_discovery(monkeypatch) -> None:
    stub = _scrape_stub(standard=1, deep=1, ats_slug=1, ats_discovery=10)
    monkeypatch.setattr(hunt, "scrape_with_stats", stub)
    _pass_through_quality_pipeline(monkeypatch)

    jobs = hunt._adaptive_region_hunt("bh", {}, {}, MagicMock(), 5, ScrapeStats())

    assert len(jobs) == 13  # 1 + 1 + 1 + 10 — every pass had to run


def test_adaptive_region_hunt_force_reincludes_previously_processed_url(monkeypatch, tmp_path) -> None:
    import job_hunter.tracking.processed_urls as tracker
    from job_hunter.tracking.repository import mark_urls_processed

    mark_urls_processed(tmp_path, {"https://example.com/standard/0"})
    monkeypatch.setattr(tracker, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(hunt, "scrape_with_stats", _scrape_stub(standard=2))
    monkeypatch.setattr(hunt, "_drop_dead_urls", lambda jobs, *_a, **_k: jobs)
    monkeypatch.setattr(hunt, "apply_pre_enrichment_quality_gate", lambda jobs, _cfg: (jobs, []))
    monkeypatch.setattr(hunt, "_enrich", lambda jobs, _cfg: jobs)
    monkeypatch.setattr(hunt, "screen_jobs_by_rules", lambda jobs, _cfg: (jobs, []))

    without_force = hunt._adaptive_region_hunt("bh", {}, {}, MagicMock(), 2, ScrapeStats(), force=False)
    with_force = hunt._adaptive_region_hunt("bh", {}, {}, MagicMock(), 2, ScrapeStats(), force=True)

    assert len(without_force) == 1  # the previously-processed URL was filtered out
    assert len(with_force) == 2  # --force re-includes it
    assert "https://example.com/standard/0" in {j["url"] for j in with_force}


def test_adaptive_region_remains_under_target_and_reports_clearly(monkeypatch, caplog) -> None:
    stub = _scrape_stub(standard=1, deep=1, ats_slug=1, ats_discovery=1)
    monkeypatch.setattr(hunt, "scrape_with_stats", stub)
    _pass_through_quality_pipeline(monkeypatch)

    with caplog.at_level("INFO"):
        jobs = hunt._adaptive_region_hunt("bh", {}, {}, MagicMock(), 15, ScrapeStats())

    assert len(jobs) == 4
    assert any("status=under_target" in r.message and "bh" in r.message for r in caplog.records)


def test_global_cap_does_not_starve_smaller_regions(monkeypatch) -> None:
    """A large region meeting its target in pass 1 must not stop a smaller
    region from running its own full escalation."""
    region_calls: dict[str, list[str | None]] = {"de": [], "bh": []}

    def fake_adaptive(region_key, _api_config, _scoring_config, _url_liveness, _target, _stats, **_kwargs):
        if region_key == "de":
            region_calls["de"].append("standard")
            return [p.model_dump() for p in _fake_postings(20, "de")]
        # Bahrain needs every pass to reach target — simulate by recording each
        # pass name via a nested fake scrape call sequence.
        for pass_name in ("standard", "deep_boards", "ats_slug", "ats_discovery"):
            region_calls["bh"].append(pass_name)
        return [p.model_dump() for p in _fake_postings(3, "bh")]

    monkeypatch.setattr(hunt, "_adaptive_region_hunt", fake_adaptive)
    monkeypatch.setattr(
        hunt,
        "enabled_regions",
        lambda _config, _region: {"de": {"country": "DE"}, "bh": {"country": "BH"}},
    )
    monkeypatch.setattr(hunt, "load_search_config", lambda: {})

    jobs, _existing_urls, _existing_titles = hunt.run_hunt({"region": None}, {}, {}, MagicMock())

    assert len(region_calls["de"]) == 1
    assert region_calls["bh"] == ["standard", "deep_boards", "ats_slug", "ats_discovery"]
    assert len(jobs) == 23  # 20 (de) + 3 (bh) — bh's jobs are not dropped just because de met target first


def test_adaptive_hunt_three_regions_uneven_supply_respects_downstream_batch_size(monkeypatch) -> None:
    """DE/BH/SG integration: DE has ample supply and meets target in pass 1, SG
    needs ATS discovery to reach target, BH has genuinely limited supply and
    stays under target even after every pass — each region gets its fair
    escalation regardless of the others, and the combined pool still respects
    the existing downstream batch_size when sliced by build_candidate_batch."""
    from job_hunter.agent_context.batch import build_candidate_batch

    # (region -> pass key -> candidate count for that pass)
    supply = {
        "de": {"fast": 8},  # meets target=5 immediately
        "sg": {"fast": 1, "deep": 1, "ats_slug": 1, "ats_discovery": 6},  # needs every pass
        "bh": {"fast": 1, "deep": 1, "ats_slug": 1, "ats_discovery": 1},  # exhausts passes, stays under target
    }
    counters = {"de": 0, "sg": 0, "bh": 0}

    def fake_scrape(
        region=None, *, depth="standard", include_boards=True, include_ats_slug=True, include_ats_discovery=True
    ):
        if include_boards and depth == "fast":
            key = "fast"
        elif include_boards and depth == "deep":
            key = "deep"
        elif not include_boards and not include_ats_discovery:
            key = "ats_slug"
        elif not include_boards and not include_ats_slug:
            key = "ats_discovery"
        else:
            key = ""
        n = supply.get(region, {}).get(key, 0)
        counters[region] += 1
        prefix = f"{region}-{key}-{counters[region]}"
        return _fake_postings(n, prefix), ScrapeStats()

    monkeypatch.setattr(hunt, "scrape_with_stats", fake_scrape)
    monkeypatch.setattr(hunt, "load_search_config", lambda: {})
    monkeypatch.setattr(
        hunt,
        "enabled_regions",
        lambda _config, _region: {
            "de": {"country": "DE"},
            "bh": {"country": "BH"},
            "sg": {"country": "SG"},
        },
    )
    _pass_through_quality_pipeline(monkeypatch)

    scoring_config = {"scoring": {"batch_size": 5}}
    jobs, _existing_urls, _existing_titles = hunt.run_hunt({"region": None}, {}, scoring_config, MagicMock())

    # DE reached target in pass 1 (8 >= 5); SG needed all 4 passes (1+1+1+6=9 >= 5);
    # BH exhausted all 4 passes and stayed under target (1+1+1+1=4 < 5).
    assert len(jobs) == 8 + 9 + 4

    # Downstream batching still caps at batch_size regardless of how many
    # quality candidates the adaptive hunt produced across all three regions.
    batch = build_candidate_batch({"jobs": jobs}, batch_size=5)
    assert batch["count"] == 5
    assert len(batch["jobs"]) == 5


def test_scrape_only_reaches_target_only_after_deep_pass_and_writes_db(monkeypatch, tmp_path) -> None:
    """run_hunt_scrape_only (agent/scrape-only mode) must reuse the same adaptive
    per-region escalation as run_hunt: the standard pass alone is short of the
    conftest batch_size=15 target, so the deep pass has to run before target is
    met, and only then are the accumulated quality jobs written to the DB."""
    from job_hunter.tracking.repository import get_discovered_jobs

    calls: list[str | None] = []
    stub = _scrape_stub(standard=5, deep=11, ats_slug=20, ats_discovery=20)

    def tracking_stub(region=None, **kwargs):
        calls.append(kwargs.get("depth"))
        return stub(region=region, **kwargs)

    monkeypatch.setattr(hunt, "scrape_with_stats", tracking_stub)
    _pass_through_quality_pipeline(monkeypatch)
    monkeypatch.setattr(hunt, "load_search_config", lambda: {})
    monkeypatch.setattr(hunt, "enabled_regions", lambda _config, _region: {"bh": {"country": "BH"}})
    monkeypatch.setattr(hunt, "load_cached_candidate_urls", lambda: set())
    monkeypatch.setattr(hunt, "save_cached_candidate_urls", lambda _urls: None)

    run_id, count, _stats = hunt.run_hunt_scrape_only("bh", tmp_path, api_config={})

    assert calls == ["fast", "deep"]  # standard pass alone (5) is under the target=15; deep pass fills the gap
    assert count == 16  # 5 (standard) + 11 (deep)
    db_jobs = get_discovered_jobs(tmp_path, run_id=run_id)
    assert len(db_jobs) == 16


def test_agent_mode_uses_adaptive_scraping(monkeypatch, tmp_path) -> None:
    """run(inp) with mode="agent" must escalate per region: DE meets the target
    in the standard pass, BH is short until deep_boards, and insert_jobs receives
    the combined adaptive result."""
    from job_hunter.models import HuntInput

    calls: list[tuple[str | None, str | None]] = []
    supply = {"de": {"fast": 20}, "bh": {"fast": 2, "deep": 20}}
    counters = {"de": 0, "bh": 0}

    def fake_scrape(
        region=None, *, depth="standard", include_boards=True, include_ats_slug=True, include_ats_discovery=True
    ):
        if include_boards and depth == "fast":
            key = "fast"
        elif include_boards and depth == "deep":
            key = "deep"
        elif not include_boards and not include_ats_discovery:
            key = "ats_slug"
        else:
            key = "ats_discovery"
        calls.append((region, key))
        n = supply.get(region, {}).get(key, 0)
        counters[region] += 1
        return _fake_postings(n, f"{region}-{key}-{counters[region]}"), ScrapeStats()

    inserted: list[list[dict]] = []
    monkeypatch.setattr(hunt, "scrape_with_stats", fake_scrape)
    _pass_through_quality_pipeline(monkeypatch)
    monkeypatch.setattr(hunt, "load_search_config", lambda: {})
    monkeypatch.setattr(
        hunt, "enabled_regions", lambda _config, _region: {"de": {"country": "DE"}, "bh": {"country": "BH"}}
    )
    monkeypatch.setattr(hunt, "insert_jobs", lambda _root, jobs, run_id: inserted.append(jobs) or len(jobs))
    monkeypatch.setattr(hunt, "load_cached_candidate_urls", lambda: set())
    monkeypatch.setattr(hunt, "save_cached_candidate_urls", lambda _urls: None)

    out = hunt.run(HuntInput(region_key="all", mode="agent"))

    # conftest batch_size=15: DE meets it in pass 1; BH needs deep_boards.
    assert [c for c in calls if c[0] == "de"] == [("de", "fast")]
    assert [c for c in calls if c[0] == "bh"] == [("bh", "fast"), ("bh", "deep")]
    assert len(inserted) == 1
    assert len(inserted[0]) == 20 + 2 + 20
    assert out.run_id


def test_region_meeting_target_via_ats_discovery_is_not_under_target(monkeypatch) -> None:
    stub = _scrape_stub(standard=1, deep=1, ats_slug=1, ats_discovery=10)
    monkeypatch.setattr(hunt, "scrape_with_stats", stub)
    _pass_through_quality_pipeline(monkeypatch)
    stats = ScrapeStats()

    jobs = hunt._adaptive_region_hunt("bh", {}, {}, MagicMock(), 5, stats)

    assert len(jobs) == 13
    assert stats.under_target_regions == []


def test_under_target_region_logs_exhausted_passes(monkeypatch, caplog) -> None:
    stub = _scrape_stub(standard=1, deep=1, ats_slug=1, ats_discovery=1)
    monkeypatch.setattr(hunt, "scrape_with_stats", stub)
    _pass_through_quality_pipeline(monkeypatch)
    stats = ScrapeStats()

    with caplog.at_level("INFO"):
        hunt._adaptive_region_hunt("bh", {}, {}, MagicMock(), 15, stats)

    assert stats.under_target_regions == ["bh"]
    under = [r.message for r in caplog.records if "status=under_target" in r.message]
    assert under and "exhausted_passes=['standard', 'deep_boards', 'ats_slug', 'ats_discovery']" in under[0]


def test_ats_discovery_jobs_keep_region_through_adaptive_hunt(monkeypatch) -> None:
    """A job found only by the ats_discovery pass must reach the final adaptive
    result with its source region intact (region propagation, task 8)."""

    def fake_scrape(
        region=None, *, depth="standard", include_boards=True, include_ats_slug=True, include_ats_discovery=True
    ):
        if not include_boards and not include_ats_slug:  # the ats_discovery pass
            return [_posting(url="https://jobs.lever.co/acme/bh-1", region="BH")], ScrapeStats()
        return [], ScrapeStats()

    monkeypatch.setattr(hunt, "scrape_with_stats", fake_scrape)
    _pass_through_quality_pipeline(monkeypatch)

    jobs = hunt._adaptive_region_hunt("BH", {}, {}, MagicMock(), 5, ScrapeStats())

    assert len(jobs) == 1
    assert jobs[0]["region"] == "BH"
