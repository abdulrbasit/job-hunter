"""Tests for generic search-provider routing behavior."""

from concurrent.futures import ThreadPoolExecutor
from typing import Never

from job_hunter.config.defaults import HTTP_DEFAULTS
from job_hunter.sources import search
from job_hunter.sources.search import (
    ats_discovery as _ats_mod,
)
from job_hunter.sources.search import (
    fetchers as _fetchers_mod,
)
from job_hunter.sources.search import (
    providers as _prov_mod,
)
from job_hunter.sources.search import (
    router as _router_mod,
)


class FailingProvider(search.SearchProvider):
    name = "failing"

    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str, region_config: dict, count: int = 10) -> Never:
        self.calls += 1
        raise RuntimeError("boom")


class EmptyProvider(search.SearchProvider):
    name = "empty"

    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str, region_config: dict, count: int = 10):
        self.calls += 1
        return []


class StaticProvider(search.SearchProvider):
    name = "static"

    def search(self, query: str, region_config: dict, count: int = 10):
        return [
            search.SearchResult(
                url="https://jobs.smartrecruiters.com/TestCo/123456-product-manager",
                title="Product Manager",
                description="Dublin product role",
                source="SearXNG",
            ),
            search.SearchResult(
                url="https://jobs.smartrecruiters.com/TestCo",
                title="Product Manager jobs",
                description="Listing page",
                source="SearXNG",
            ),
        ]


def test_default_provider_orders_reserve_semantic_search_for_ats_discovery() -> None:
    config = HTTP_DEFAULTS["search_providers"]

    assert config["order"] == ["searxng", "brave"]
    assert config["ats_discovery_order"] == ["searxng", "brave", "exa"]


def test_router_skips_provider_after_configured_consecutive_failures() -> None:
    search._PROVIDER_STATE.failures.clear()
    failing = FailingProvider()
    fallback = EmptyProvider()
    router = search.SearchRouter(providers=[failing, fallback])
    router.max_consecutive_failures = 3

    for _ in range(4):
        router.search("query", {}, count=1)

    assert failing.calls == 3
    assert fallback.calls == 4


def test_router_failure_counter_is_thread_safe() -> None:
    search._PROVIDER_STATE.failures.clear()
    router = search.SearchRouter(providers=[FailingProvider()])
    router.max_consecutive_failures = 100

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: router.search("query", {}, count=1), range(20)))

    assert search._PROVIDER_STATE.failures["failing"] == 20


def test_canonicalize_url_strips_tracking_for_dedupe() -> None:
    left = "https://www.example.com/jobs/123/?utm_source=x&b=2&a=1#details"
    right = "https://example.com/jobs/123?a=1&b=2"

    assert search.canonicalize_url(left) == search.canonicalize_url(right)


def test_discover_ats_jobs_by_search_extracts_expanded_ats_shapes(monkeypatch) -> None:
    monkeypatch.setattr(_router_mod._PROVIDER_STATE, "run_disabled", set())

    class FakeRouter:
        def __init__(self, provider_order, **kwargs) -> None:
            self.provider_order = provider_order

        def search(self, query: str, region_config: dict, count: int = 10):
            assert self.provider_order == ["searxng", "brave"]
            return StaticProvider().search(query, region_config, count=count)

    monkeypatch.setattr(_ats_mod, "ProviderSearchRouter", FakeRouter)
    monkeypatch.setattr(
        _ats_mod,
        "_search_config",
        lambda: {
            "ats_discovery": {
                "enabled": True,
                "sources": ["smartrecruiters"],
                "results_per_query": 10,
            }
        },
    )
    monkeypatch.setattr(_ats_mod, "_enrich_ats_discovery_job", lambda _url: None)

    jobs = search.discover_ats_jobs_by_search(
        ["Product Manager"],
        {"dublin": {"location": "Dublin"}},
        provider_order=["searxng", "brave"],
    )

    assert len(jobs) == 1
    assert jobs[0]["url"] == "https://jobs.smartrecruiters.com/TestCo/123456-product-manager"
    assert jobs[0]["company"] == "Testco"
    assert jobs[0]["source"] == "SearXNG ATS discovery: smartrecruiters"


def test_discover_ats_jobs_respects_query_caps(monkeypatch) -> None:
    monkeypatch.setattr(_router_mod._PROVIDER_STATE, "run_disabled", set())
    queries = []

    class FakeRouter:
        def __init__(self, provider_order, **kwargs) -> None:
            self.provider_order = provider_order

        def search(self, query: str, region_config: dict, count: int = 10):
            queries.append(query)
            return []

    monkeypatch.setattr(_ats_mod, "ProviderSearchRouter", FakeRouter)
    monkeypatch.setattr(
        _ats_mod,
        "_search_config",
        lambda: {
            "ats_discovery": {
                "enabled": True,
                "sources": ["greenhouse", "lever", "ashby"],
                "results_per_query": 10,
                "max_queries_per_region": 2,
                "max_total_queries": 3,
            }
        },
    )
    monkeypatch.setattr(_ats_mod, "_enrich_ats_discovery_job", lambda _url: None)

    jobs = search.discover_ats_jobs_by_search(
        ["Product Manager", "Product Owner"],
        {
            "berlin": {"location": "Berlin"},
            "dublin": {"location": "Dublin"},
        },
    )

    assert jobs == []
    assert len(queries) == 3


def test_brave_provider_uses_shared_search_provider_timeout(monkeypatch) -> None:
    sections = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"web": {"results": []}}

    def fake_timeout(section: str) -> int:
        sections.append(section)
        return 7

    def fake_get(*args, **kwargs):
        assert kwargs["timeout"] == 7
        return FakeResponse()

    monkeypatch.setattr(_prov_mod, "_timeout", fake_timeout)
    monkeypatch.setattr(search.requests, "get", fake_get)

    assert search.BraveProvider().search("query", {}, count=1) == []
    assert sections == ["search_providers"]


# ── Task 2: Exhausted provider fallback ──────────────────────────────────────


class ExhaustedProvider(search.SearchProvider):
    """Simulates a provider whose quota is exhausted (reserve_api_call returns False)."""

    name = "exhausted_provider"

    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str, region_config: dict, count: int = 10):
        self.calls += 1
        return []


class GoodProvider(search.SearchProvider):
    """Provider that always returns one result."""

    name = "good_provider"

    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str, region_config: dict, count: int = 10):
        self.calls += 1
        return [
            search.SearchResult(
                url="https://example.com/job/1",
                title="Product Manager",
                description="Great role",
                source="good_provider",
            )
        ]


def test_router_skips_exhausted_provider_and_continues_to_next(monkeypatch) -> None:
    """When a provider is pre-marked exhausted, the router skips it and tries the next one."""
    search._PROVIDER_STATE.failures.clear()

    exhausted = ExhaustedProvider()
    good = GoodProvider()

    # Mark exhausted_provider as quota-exhausted without a real state file
    monkeypatch.setattr(
        search.SearchRouter,
        "_is_exhausted",
        lambda self, provider: provider.name == "exhausted_provider",
    )

    router = search.SearchRouter(providers=[exhausted, good])
    results = router.search("query", {}, count=5)

    assert exhausted.calls == 0, "exhausted provider must not be called"
    assert good.calls == 1
    assert len(results) == 1


def test_router_quota_exhaustion_exception_does_not_suppress_next_provider(monkeypatch) -> None:
    """A quota-exhaustion exception resets the failure counter and continues to the next provider."""
    search._PROVIDER_STATE.failures.clear()

    class QuotaProvider(search.SearchProvider):
        name = "quota_provider"
        calls = 0

        def search(self, query, region_config, count=10) -> Never:
            self.calls += 1

            class FakeResp:
                status_code = 402
                reason = "Payment Required"
                text = "quota exceeded"

            exc = Exception("quota exceeded")
            exc.response = FakeResp()
            raise exc

    quota = QuotaProvider()
    good = GoodProvider()

    # Treat any exception from quota_provider as quota-exhausted

    monkeypatch.setattr(
        _router_mod,
        "is_api_quota_exhausted",
        lambda exc: getattr(getattr(exc, "response", None), "status_code", None) == 402,
    )
    monkeypatch.setattr(
        search.SearchRouter,
        "_is_exhausted",
        lambda self, provider: False,  # not pre-exhausted; let the exception path trigger
    )

    router = search.SearchRouter(providers=[quota, good])
    results = router.search("query", {}, count=5)

    assert quota.calls == 1
    assert good.calls == 1
    assert len(results) == 1
    # Failure counter for quota_provider must be 0 (reset after quota exc, not incremented)
    assert search._PROVIDER_STATE.failures.get("quota_provider", 0) == 0


def test_router_no_key_provider_skipped_silently() -> None:
    """A provider with no credentials is skipped at DEBUG level without noisy warnings."""
    search._PROVIDER_STATE.failures.clear()

    class NoKeyProvider(search.SearchProvider):
        name = "no_key"
        calls = 0

        def enabled(self) -> bool:
            return False

        def search(self, query, region_config, count=10):
            self.calls += 1
            return []

    no_key = NoKeyProvider()
    good = GoodProvider()

    router = search.SearchRouter(providers=[no_key, good])
    results = router.search("query", {}, count=5)

    assert no_key.calls == 0
    assert good.calls == 1
    assert len(results) == 1


# ── T-7: Search exhaustion detection ─────────────────────────────────────────


def _reset_exhaustion_state() -> None:
    """Reset module-level exhaustion counters to their defaults."""
    with _router_mod._PROVIDER_STATE.searxng_zero_lock:
        _router_mod._PROVIDER_STATE.searxng_consecutive_zeros = 0
        _router_mod._PROVIDER_STATE.ats_only_logged = False
    _router_mod._PROVIDER_STATE.run_disabled.clear()


def test_all_providers_exhausted_returns_false_with_budget(monkeypatch) -> None:
    """Returns False when an ATS discovery provider is available."""
    _reset_exhaustion_state()
    monkeypatch.setattr(_router_mod._PROVIDER_STATE, "run_disabled", set())
    monkeypatch.setattr(search.BraveProvider, "enabled", lambda self: True)

    result = search.all_providers_exhausted()
    assert result is False

    _reset_exhaustion_state()


def test_all_providers_exhausted_returns_true_when_all_exhausted(monkeypatch) -> None:
    """Returns True when ATS discovery providers are unavailable."""
    _reset_exhaustion_state()
    monkeypatch.setattr(_router_mod._PROVIDER_STATE, "run_disabled", {"brave", "exa"})
    monkeypatch.setattr(search.SearxngProvider, "enabled", lambda self: False)

    result = search.all_providers_exhausted()
    assert result is True

    _reset_exhaustion_state()


def test_discover_ats_jobs_by_search_returns_empty_when_exhausted(monkeypatch, caplog) -> None:
    """discover_ats_jobs_by_search() returns [] and logs when all providers exhausted."""
    import logging

    _reset_exhaustion_state()

    monkeypatch.setattr(_ats_mod, "all_providers_exhausted", lambda api_config=None: True)
    monkeypatch.setattr(
        _ats_mod,
        "_search_config",
        lambda: {"ats_discovery": {"enabled": True}},
    )
    monkeypatch.setattr(_ats_mod, "get_api_config", lambda: {})

    with caplog.at_level(logging.INFO, logger=_ats_mod.logger.name):
        result = search.discover_ats_jobs_by_search(
            ["Software Engineer"],
            {"EU": {"location": "Europe"}},
        )

    assert result == []
    assert any("[search-discovery] skipped: all providers exhausted" in record.message for record in caplog.records)

    _reset_exhaustion_state()


def test_searxng_uses_configured_engines_without_zero_penalty(monkeypatch) -> None:
    """Empty SearXNG results should not globally mark the provider as unavailable."""
    import job_hunter.sources.search as sp

    _reset_exhaustion_state()
    calls = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self):
            return {"results": []}

    def fake_get(*args, **kwargs):
        calls.append(kwargs["params"])
        return FakeResponse()

    monkeypatch.setattr(search.requests, "get", fake_get)
    monkeypatch.setattr(
        _prov_mod,
        "_search_config",
        lambda: {
            "searxng_base_url": "http://localhost:8888",
            "searxng_categories": "general",
            "searxng_engines": ["bing", "duckduckgo", "brave"],
        },
    )

    provider = sp.SearxngProvider()
    provider.search("test query", {})

    with _router_mod._PROVIDER_STATE.searxng_zero_lock:
        count = _router_mod._PROVIDER_STATE.searxng_consecutive_zeros
    assert count == 0
    assert calls[0]["categories"] == "general"
    assert calls[0]["engines"] == "bing,duckduckgo,brave"

    _reset_exhaustion_state()


def test_ats_search_queries_split_grouped_site_queries() -> None:
    queries = search._ats_search_queries(
        "site:boards.greenhouse.io OR site:job-boards.greenhouse.io",
        "Product Manager",
        "Berlin",
    )

    assert queries == [
        'site:boards.greenhouse.io "Product Manager" "Berlin"',
        'site:boards.greenhouse.io "Product Manager"',
        'site:job-boards.greenhouse.io "Product Manager" "Berlin"',
        'site:job-boards.greenhouse.io "Product Manager"',
    ]


def test_discover_ats_jobs_enriches_generic_search_title(monkeypatch) -> None:
    monkeypatch.setattr(_router_mod._PROVIDER_STATE, "run_disabled", set())

    class FakeRouter:
        def __init__(self, provider_order, **kwargs) -> None:
            self.provider_order = provider_order

        def search(self, query: str, region_config: dict, count: int = 10):
            return [
                search.SearchResult(
                    url="https://boards.greenhouse.io/acme/jobs/123",
                    title="Jobs at Acme",
                    description="Current openings",
                    source="SearXNG",
                )
            ]

    monkeypatch.setattr(_ats_mod, "ProviderSearchRouter", FakeRouter)
    monkeypatch.setattr(
        _ats_mod,
        "_search_config",
        lambda: {
            "ats_discovery": {
                "enabled": True,
                "sources": ["greenhouse"],
                "results_per_query": 10,
            }
        },
    )
    monkeypatch.setattr(
        _ats_mod,
        "_enrich_ats_discovery_job",
        lambda _url: {
            "title": "Product Manager",
            "company": "Acme",
            "location": "Berlin",
            "posted_date_text": "2026-06-01",
            "snippet": "Own product discovery.",
        },
    )

    jobs = search.discover_ats_jobs_by_search(
        ["Product Manager"],
        {"berlin": {"location": "Berlin"}},
        provider_order=["searxng"],
    )

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Product Manager"
    assert jobs[0]["source"] == "SearXNG ATS discovery: greenhouse API"


def test_lightpanda_career_jobs_parse_rendered_html(monkeypatch) -> None:
    class Completed:
        returncode = 0
        stdout = '<a href="/jobs/product-manager-berlin">Product Manager</a>'

    monkeypatch.setattr(search.shutil, "which", lambda _name: "lightpanda")
    monkeypatch.setattr(search.subprocess, "run", lambda *a, **k: Completed())
    monkeypatch.setattr(
        _fetchers_mod,
        "get_api_config",
        lambda: {"http": {"lightpanda": {"timeout_seconds": 8}}},
    )

    jobs = search.fetch_lightpanda_career_jobs(
        {"name": "ExampleCo", "career_url": "https://example.com/careers", "location": "Berlin"},
        ["Product Manager"],
    )

    assert len(jobs) == 1
    assert jobs[0]["source"] == "Lightpanda career page"


def test_firecrawl_career_jobs_require_key_and_budget(monkeypatch) -> None:
    calls = {"reserved": 0, "posted": 0}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"data": {"markdown": "[Product Manager](https://example.com/jobs/product-manager-berlin)"}}

    def reserve(provider: str) -> bool:
        calls["reserved"] += 1
        assert provider == "firecrawl"
        return True

    def post(*args, **kwargs):
        calls["posted"] += 1
        assert kwargs["json"]["formats"] == ["markdown"]
        return Response()

    monkeypatch.setattr(_fetchers_mod, "FIRECRAWL_API_KEY", "key")
    monkeypatch.setattr(_fetchers_mod, "reserve_api_call", reserve)
    monkeypatch.setattr(search.requests, "post", post)
    monkeypatch.setattr(
        _fetchers_mod,
        "get_api_config",
        lambda: {"http": {"firecrawl": {"timeout_seconds": 20}}},
    )

    jobs = search.fetch_firecrawl_career_jobs(
        {"name": "ExampleCo", "career_url": "https://example.com/careers", "location": "Berlin"},
        ["Product Manager"],
    )

    assert len(jobs) == 1
    assert jobs[0]["source"] == "Firecrawl career page"
    assert calls == {"reserved": 1, "posted": 1}
