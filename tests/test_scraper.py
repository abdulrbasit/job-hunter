"""Tests for sources/scraper — all HTTP calls are mocked.

The scraper is source-first: every configured title is searched across every
enabled source for every enabled region. There is no company list or company loop.
"""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from job_hunter.core.utils import title_matches
from job_hunter.sources import scraper
from job_hunter.sources._policy import JobPolicy
from job_hunter.sources.search_providers import canonicalize_url


@pytest.fixture(autouse=True)
def _no_preflight(monkeypatch) -> None:
    """Prevent run-start preflight from making live HTTP calls in scraper tests."""
    monkeypatch.setattr(
        "job_hunter.sources.scraper._boards.probe_search_providers",
        lambda: set(),
    )
    monkeypatch.setattr(
        "job_hunter.sources.scraper._boards.probe_job_sources",
        lambda *_args: {},
    )


CONFIG = {
    "job_titles": ["Product Manager", "Product Owner"],
    "exclusions": {
        "title_terms": ["director", "vp ", "head of product"],
        "industries": ["banking", "casino"],
        "languages": ["german"],
        "companies": [],
    },
    "regions": {
        "berlin": {
            "enabled": True,
            "country": "DE",
            "search_lang": "en",
            "location": "Berlin",
        }
    },
    "search": {"llm_search": {"enabled": False, "trigger_threshold": 15, "max_results_per_run": 20}},
}


def _policy(config: dict | None = None) -> JobPolicy:
    return JobPolicy(config or CONFIG)


_EXTERNAL_PATCHES = [
    ("job_hunter.sources.scraper._discovery.discover_ats_jobs_by_search", []),
    ("job_hunter.sources.scraper._discovery.fetch_ai_web_search_jobs", []),
    ("job_hunter.sources.jobspy_source.JobSpySource.fetch", []),
    ("job_hunter.sources.himalayas_source.HimalayasSource.fetch", []),
    ("job_hunter.sources.remotive_source.RemotiveSource.fetch", []),
    ("job_hunter.sources.the_muse_source.TheMuseSource.fetch", []),
    ("job_hunter.sources.jobicy_source.JobicySource.fetch", []),
    ("job_hunter.sources.remoteok_source.RemoteOKSource.fetch", []),
    ("job_hunter.sources.weworkremotely_source.WeWorkRemotelySource.fetch", []),
    ("job_hunter.sources.mycareersfuture_source.MyCareersFutureSource.fetch", []),
    ("job_hunter.sources.jobbank_source.JobBankSource.fetch", []),
    ("job_hunter.sources.glints_source.GlintsSource.fetch", []),
    ("job_hunter.sources.gulftalent_source.GulfTalentSource.fetch", []),
    ("job_hunter.sources.jobstreet_source.JobStreetSource.fetch", []),
    ("job_hunter.sources.jooble_source.JoobleSource.fetch", []),
    ("job_hunter.sources.arbeitsagentur_source.ArbeitsagenturSource.fetch", []),
    ("job_hunter.sources.job_boards.ArbeitnowSource.fetch", []),
    ("job_hunter.sources.job_boards.JSearchSource.fetch", []),
    ("job_hunter.sources.adzuna_source.AdzunaSource.fetch", []),
    ("job_hunter.sources.reed_source.ReedSource.fetch", []),
    ("job_hunter.sources.careerjet_source.CareerjetSource.fetch", []),
    ("job_hunter.sources.workingnomads_source.WorkingNomadsSource.fetch", []),
    ("job_hunter.sources.scraper._boards.load_cached_candidate_urls", set()),
    ("job_hunter.sources.scraper._boards.save_cached_candidate_urls", None),
]


@pytest.fixture(autouse=True)
def _disable_external_scrape_paths():
    """Silence all external I/O so only the paths under test are exercised."""
    with ExitStack() as stack:
        for target, return_val in _EXTERNAL_PATCHES:
            if return_val is None:
                stack.enter_context(patch(target))
            else:
                stack.enter_context(patch(target, return_value=return_val))
        yield


def _make_posting(url, title="Product Manager", company="TestCo", snippet="PM role"):
    from job_hunter.models import JobPosting

    return JobPosting(url=url, title=title, company=company, snippet=snippet, posted="", source="test")


def _make_response(json_data=None, text=None, status_code=200, raise_error=False):
    resp = MagicMock()
    resp.status_code = status_code
    if raise_error:
        resp.raise_for_status.side_effect = Exception("HTTP error")
    else:
        resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    resp.text = text
    return resp


def _mock_http(results, status=200):
    return _make_response(json_data={"web": {"results": results}}, status_code=status)


# ── is_valid_job_url() ───────────────────────────────────────────────────────


def test_valid_job_url_accepts_deep_path() -> None:
    assert _policy().is_valid_job_url("https://boards.greenhouse.io/deliveryhero/jobs/12345") is True


def test_valid_job_url_accepts_lever_slug() -> None:
    assert _policy().is_valid_job_url("https://jobs.lever.co/getyourguide/product-manager-berlin") is True


def test_valid_job_url_rejects_domain_root() -> None:
    assert _policy().is_valid_job_url("https://jobs.testco.com") is False


def test_valid_job_url_rejects_root_slash() -> None:
    assert _policy().is_valid_job_url("https://jobs.testco.com/") is False


def test_valid_job_url_rejects_listing_page_careers() -> None:
    assert _policy().is_valid_job_url("https://company.com/careers") is False


def test_valid_job_url_rejects_listing_page_jobs() -> None:
    assert _policy().is_valid_job_url("https://company.com/jobs") is False


def test_valid_job_url_rejects_single_segment_ats() -> None:
    assert _policy().is_valid_job_url("https://boards.greenhouse.io/deliveryhero") is False


def test_valid_job_url_accepts_two_segment_path() -> None:
    assert _policy().is_valid_job_url("https://jobs.testco.com/en/job/12345") is True


def test_excluded_url_patterns_are_configured() -> None:
    assert _policy({}).is_excluded_url("https://www.linkedin.com/jobs/search?keywords=pm") is True
    assert _policy({}).is_excluded_url("https://www.linkedin.com/jobs/view/123") is False


# ── is_stale_posting() ───────────────────────────────────────────────────────


def test_stale_posting_detects_no_longer_available() -> None:
    assert _policy().is_stale_posting("PM role", "This job is no longer available") is True


def test_stale_posting_detects_filled() -> None:
    assert _policy().is_stale_posting("PM role", "The position has been filled") is True


def test_stale_posting_passes_active_job() -> None:
    assert _policy().is_stale_posting("PM Berlin", "Join our growing team in Berlin") is False


# ── Language filtering ────────────────────────────────────────────────────────


def test_german_language_heuristic_rejects_adzuna_style_description() -> None:
    snippet = (
        "Mitte, Berlin - Deine Mission In dieser Position treibst du die strategische "
        "Weiterentwicklung unserer Cloud aktiv voran. An der Schnittstelle von User "
        "Experience, Tech und Business gestaltest du Produkte, die echten Mehrwert "
        "schaffen. Mit deinem Blick fuer das Ganze sorgst du fuer klare Priorisierung."
    )
    assert _policy().is_german("Product Manager:in", snippet) is True


def test_german_language_heuristic_allows_english_berlin_description() -> None:
    snippet = (
        "Berlin, Germany - You will own product discovery for a cloud platform, work "
        "with engineering and design, define priorities, and speak with customers to "
        "shape measurable outcomes for product teams."
    )
    assert _policy().is_german("Product Manager", snippet) is False


def test_german_language_filter_disabled_when_not_in_excluded_languages() -> None:
    config = {
        **CONFIG,
        "exclusions": {**CONFIG["exclusions"], "languages": []},
    }
    snippet = (
        "Berlin, Deutschland - Deine kuenftigen Aufgaben umfassen Verantwortung "
        "fuer Aufbau, Struktur, Priorisierung und kontinuierliches Refinement des "
        "Product Backlogs sowie die Uebersetzung von Anforderungen in klare Aufgaben."
    )
    assert _policy(config).is_german("Product Owner", snippet) is False


def test_language_indicator_triggers_exclusion() -> None:
    snippet = "wir suchen einen Product Manager für unser Team"
    assert _policy().is_german("PM", snippet) is True


# ── brave_search() ───────────────────────────────────────────────────────────


def test_brave_search_returns_results() -> None:
    results = [{"url": "https://jobs.testco.com/en/pm", "title": "PM", "description": "role"}]
    with patch(
        "job_hunter.sources.search_providers.providers.requests.get",
        return_value=_mock_http(results),
    ):
        out = scraper.brave_search("query", {"country": "DE", "search_lang": "en"})
    assert len(out) == 1
    assert out[0]["url"] == "https://jobs.testco.com/en/pm"


def test_brave_search_returns_empty_on_no_results() -> None:
    with patch(
        "job_hunter.sources.search_providers.providers.requests.get",
        return_value=_mock_http([]),
    ):
        out = scraper.brave_search("query", {"country": "DE"})
    assert out == []


def test_brave_search_raises_on_http_error() -> None:
    with patch(
        "job_hunter.sources.search_providers.providers.requests.get", return_value=_make_response(raise_error=True)
    ):
        with pytest.raises(Exception):  # noqa: B017
            scraper.brave_search("query", {"country": "DE"})


def test_brave_search_omits_unsupported_country_codes() -> None:
    results = [{"url": "https://jobs.example.com/en/pm", "title": "PM", "description": "role"}]
    with patch(
        "job_hunter.sources.search_providers.providers.requests.get", return_value=_mock_http(results)
    ) as mock_get:
        scraper.brave_search("query", {"country": "QA", "search_lang": "en"})

    call_params = mock_get.call_args[1]["params"]
    assert "country" not in call_params
    assert call_params["search_lang"] == "en"


# ── scrape() — source-first behavior ─────────────────────────────────────────


def test_scrape_returns_empty_when_no_job_titles() -> None:
    config = {**CONFIG, "job_titles": []}
    with patch("job_hunter.sources.scraper._boards.load_search_config", return_value=config):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_returns_empty_when_no_enabled_regions() -> None:
    config = {
        **CONFIG,
        "regions": {"berlin": {"enabled": False, "country": "DE", "location": "Berlin"}},
    }
    with patch("job_hunter.sources.scraper._boards.load_search_config", return_value=config):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_runs_ats_discovery_and_accepts_results() -> None:
    discovery_job = {
        "title": "Product Manager",
        "company": "DiscoveryCo",
        "url": "https://jobs.lever.co/discoveryco/12345678-1234-1234-1234-123456789abc",
        "posted": "",
        "snippet": "PM role at DiscoveryCo",
        "source": "SearXNG ATS discovery: lever",
    }
    with (
        patch("job_hunter.sources.scraper._boards.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter.sources.scraper._discovery.discover_ats_jobs_by_search",
            return_value=[discovery_job],
        ),
    ):
        jobs = scraper.scrape()
    assert len(jobs) == 1
    assert jobs[0].company == "DiscoveryCo"


def test_scrape_deduplicates_same_url_across_sources() -> None:
    posting = _make_posting("https://jobs.testco.com/en/pm")
    posting2 = _make_posting("https://jobs.testco.com/en/pm")

    with (
        patch("job_hunter.sources.scraper._boards.load_search_config", return_value=CONFIG),
        patch("job_hunter.sources.jobspy_source.JobSpySource.fetch", return_value=[posting]),
        patch(
            "job_hunter.sources.himalayas_source.HimalayasSource.fetch",
            return_value=[posting2],
        ),
    ):
        jobs = scraper.scrape()

    urls = [j.url for j in jobs]
    assert len(urls) == len(set(urls))
    assert len(jobs) == 1


def test_scrape_deduplicates_canonical_urls() -> None:
    p1 = _make_posting("https://www.jobs.testco.com/en/pm?utm_source=x&a=1")
    p2 = _make_posting("https://jobs.testco.com/en/pm?a=1", title="Product Manager duplicate")

    with (
        patch("job_hunter.sources.scraper._boards.load_search_config", return_value=CONFIG),
        patch("job_hunter.sources.jobspy_source.JobSpySource.fetch", return_value=[p1]),
        patch("job_hunter.sources.himalayas_source.HimalayasSource.fetch", return_value=[p2]),
    ):
        jobs = scraper.scrape()

    assert len(jobs) == 1


def test_scrape_applies_seniority_filter() -> None:
    senior_posting = _make_posting(
        "https://boards.greenhouse.io/testco/jobs/senior",
        title="Director of Product",
        snippet="senior leadership role",
    )
    with (
        patch("job_hunter.sources.scraper._boards.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter.sources.jobspy_source.JobSpySource.fetch",
            return_value=[senior_posting],
        ),
    ):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_applies_industry_filter() -> None:
    banking_posting = _make_posting(
        "https://boards.greenhouse.io/testco/jobs/bank",
        snippet="banking platform role",
    )
    with (
        patch("job_hunter.sources.scraper._boards.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter.sources.jobspy_source.JobSpySource.fetch",
            return_value=[banking_posting],
        ),
    ):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_applies_stale_indicator_filter() -> None:
    stale_discovery = {
        "title": "Product Manager",
        "company": "TestCo",
        "url": "https://jobs.lever.co/testco/12345",
        "snippet": "no longer available",
        "posted": "",
        "source": "ats",
    }
    with (
        patch("job_hunter.sources.scraper._boards.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter.sources.scraper._discovery.discover_ats_jobs_by_search",
            return_value=[stale_discovery],
        ),
    ):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_applies_german_language_filter_via_language_indicators() -> None:
    german_posting = _make_posting(
        "https://jobs.testco.com/en/pm",
        title="PM m/w/d",
        snippet="vollzeit",
    )
    with (
        patch("job_hunter.sources.scraper._boards.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter.sources.jobspy_source.JobSpySource.fetch",
            return_value=[german_posting],
        ),
    ):
        jobs = scraper.scrape()
    assert jobs == []


def test_scrape_skips_adzuna_german_descriptions() -> None:
    adzuna_job = {
        "title": "Product Owner",
        "company": "AdzunaCo",
        "url": "https://www.adzuna.de/details/123",
        "posted": "2026-05-26",
        "snippet": (
            "Berlin, Deutschland - Deine kuenftigen Aufgaben umfassen Verantwortung "
            "fuer Aufbau, Struktur, Priorisierung und kontinuierliches Refinement des "
            "Product Backlogs sowie die Uebersetzung von Anforderungen in klare Aufgaben."
        ),
        "source": "Adzuna",
    }
    adzuna_posting = MagicMock()
    adzuna_posting.to_dict.return_value = adzuna_job

    with (
        patch("job_hunter.sources.scraper._boards.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter.sources.adzuna_source.AdzunaSource.fetch",
            return_value=[adzuna_posting],
        ),
    ):
        jobs = scraper.scrape()

    assert jobs == []


def test_scrape_skips_cached_discovery_candidates() -> None:
    discovery_job = {
        "title": "Product Owner",
        "company": "DiscoveryCo",
        "url": "https://jobs.lever.co/discovery/12345678-1234-1234-1234-123456789abc",
        "posted": "",
        "snippet": "Discovery role",
        "source": "SearXNG ATS discovery: lever",
    }

    with (
        patch("job_hunter.sources.scraper._boards.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter.sources.scraper._discovery.discover_ats_jobs_by_search",
            return_value=[discovery_job],
        ),
        patch(
            "job_hunter.sources.scraper._boards.load_cached_candidate_urls",
            return_value={canonicalize_url(discovery_job["url"])},
        ),
        patch("job_hunter.sources.scraper._boards.save_cached_candidate_urls") as save_cache,
    ):
        jobs = scraper.scrape()

    assert jobs == []
    save_cache.assert_not_called()


def test_scrape_continues_after_source_failure() -> None:
    good_posting = _make_posting("https://boards.greenhouse.io/testco/jobs/12345")
    with (
        patch("job_hunter.sources.scraper._boards.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter.sources.jobspy_source.JobSpySource.fetch",
            side_effect=RuntimeError("jobspy boom"),
        ),
        patch(
            "job_hunter.sources.himalayas_source.HimalayasSource.fetch",
            return_value=[good_posting],
        ),
    ):
        jobs = scraper.scrape()
    assert len(jobs) == 1


# ── scrape() — LLM search gating ─────────────────────────────────────────────


def test_scrape_runs_llm_search_when_enabled_and_below_threshold() -> None:
    ai_job = {
        "title": "Product Owner",
        "company": "LinkedCo",
        "url": "https://www.linkedin.com/jobs/view/123456",
        "posted": "",
        "snippet": "Product backlog role",
        "source": "AI web search: linkedin",
    }
    config = {
        **CONFIG,
        "search": {"llm_search": {"enabled": True, "trigger_threshold": 5, "max_results_per_run": 20}},
    }
    with (
        patch("job_hunter.sources.scraper._boards.load_search_config", return_value=config),
        patch("job_hunter.sources.scraper._discovery.fetch_ai_web_search_jobs", return_value=[ai_job]),
    ):
        jobs = scraper.scrape()
    assert len(jobs) == 1
    assert jobs[0].url == ai_job["url"]
    assert jobs[0].company == ai_job["company"]


def test_scrape_skips_llm_search_when_disabled() -> None:
    ai_mock = MagicMock()
    config = {**CONFIG, "search": {"llm_search": {"enabled": False, "trigger_threshold": 15}}}
    with (
        patch("job_hunter.sources.scraper._boards.load_search_config", return_value=config),
        patch("job_hunter.sources.scraper._discovery.fetch_ai_web_search_jobs", ai_mock),
    ):
        scraper.scrape()
    ai_mock.assert_not_called()


def test_scrape_skips_llm_search_when_results_meet_threshold() -> None:
    good_posting = _make_posting("https://boards.greenhouse.io/testco/jobs/12345")
    config = {
        **CONFIG,
        "search": {"llm_search": {"enabled": True, "trigger_threshold": 1, "max_results_per_run": 20}},
    }
    with (
        patch("job_hunter.sources.scraper._boards.load_search_config", return_value=config),
        patch(
            "job_hunter.sources.himalayas_source.HimalayasSource.fetch",
            return_value=[good_posting],
        ),
        patch("job_hunter.sources.scraper._discovery.fetch_ai_web_search_jobs") as ai_mock,
    ):
        jobs = scraper.scrape()
    assert any(j.url == "https://boards.greenhouse.io/testco/jobs/12345" for j in jobs)
    ai_mock.assert_not_called()


# ── title_matches() ──────────────────────────────────────────────────────────


def test_title_matches_rejects_irrelevant_product_titles() -> None:
    filters = ["Product Manager", "Product Owner"]
    assert title_matches("Senior Product Manager", filters) is True
    assert title_matches("Technical Product Owner", filters) is True
    assert title_matches("Product Engineer", filters) is False
    assert title_matches("Working Student Product Management", filters) is False


def test_title_exclusions_are_caller_configured() -> None:
    filters = ["Product Manager"]
    assert title_matches("Product Manager Engineer", filters) is True
    assert title_matches("Product Manager Engineer", filters, ["engineer"]) is False


# ── ScrapeStats diagnostics ───────────────────────────────────────────────────


def test_scrape_stats_records_accepted_and_skipped() -> None:
    stats = scraper.ScrapeStats()
    stats.record("ats_api", attempted=3, returned=2, accepted=1, skipped=1)
    s = stats.source("ats_api")
    assert s.attempted == 3
    assert s.returned == 2
    assert s.accepted == 1
    assert s.skipped == 1


def test_scrape_stats_log_summary_does_not_raise(caplog) -> None:
    import logging

    stats = scraper.ScrapeStats()
    stats.record("test_source", attempted=1, returned=0, failed=1)
    with caplog.at_level(logging.INFO):
        stats.log_summary()
    assert any("test_source" in r.message for r in caplog.records)


def test_scrape_stats_to_dict_matches_recorded_values() -> None:
    stats = scraper.ScrapeStats()
    stats.record("jobspy", attempted=5, returned=3, accepted=2, skipped=1)
    d = stats.to_dict()
    assert d["jobspy"]["attempted"] == 5
    assert d["jobspy"]["returned"] == 3
    assert d["jobspy"]["accepted"] == 2
    assert d["jobspy"]["skipped"] == 1


def test_scrape_diagnostics_ats_discovery_success_source_failure() -> None:
    discovery_job = {
        "title": "Product Manager",
        "company": "DiscoveryCo",
        "url": "https://jobs.lever.co/discoveryco/abc123",
        "posted": "",
        "snippet": "PM role",
        "source": "SearXNG ATS discovery: lever",
    }
    with (
        patch("job_hunter.sources.scraper._boards.load_search_config", return_value=CONFIG),
        patch(
            "job_hunter.sources.scraper._discovery.discover_ats_jobs_by_search",
            return_value=[discovery_job],
        ),
        patch(
            "job_hunter.sources.jobspy_source.JobSpySource.fetch",
            side_effect=RuntimeError("jobspy boom"),
        ),
    ):
        jobs = scraper.scrape()

    assert any(j.url == discovery_job["url"] for j in jobs)
