from __future__ import annotations

import pytest
from conftest import mk_params

from job_hunter.core import utils
from job_hunter.sources import (
    jd_fetcher,
    search,
)
from job_hunter.sources.ats_urls import (
    company_name_from_url,
    detect_ats,
    extract_career_url,
)
from job_hunter.sources.boards import adzuna as adzuna_source
from job_hunter.sources.boards import jobicy as jobicy_source
from job_hunter.sources.boards import reed as reed_source
from job_hunter.sources.search import (
    ats_discovery as _ats_mod,
)
from job_hunter.sources.search import (
    router as _router_mod,
)


class ErrorResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict | None = None,
        text: str = "",
        reason: str = "",
    ) -> None:
        self.status_code = status_code
        self.payload = payload or {}
        self.text = text
        self.reason = reason

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise search.requests.exceptions.HTTPError(response=self)

    def json(self) -> dict:
        return self.payload


class FakeProvider(search.SearchProvider):
    """Injectable provider for router tests — no HTTP mocking needed."""

    def __init__(self, name: str = "fakeprov", *, enabled: bool = True, results=None, exc: Exception | None = None):
        self.name = name
        self._enabled = enabled
        self._results = results or []
        self._exc = exc
        self.calls = 0

    def enabled(self) -> bool:
        return self._enabled

    def search(self, query: str, region_config: dict, count: int = 10):
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return self._results


def _quota_error(status_code: int, text: str = "credits exhausted") -> Exception:
    return search.requests.exceptions.HTTPError(response=ErrorResponse(status_code, text=text))


def test_adzuna_source_init_uses_config_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adzuna_source, "ADZUNA_APP_ID", "config-app")
    monkeypatch.setattr(adzuna_source, "ADZUNA_API_KEY", "config-key")

    src = adzuna_source.AdzunaSource()

    assert src._app_id == "config-app"
    assert src._api_key == "config-key"


def test_reed_source_init_uses_config_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reed_source, "REED_API_KEY", "config-key")

    assert reed_source.ReedSource()._api_key == "config-key"


def test_jobicy_maps_de_region_to_geo_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "jobs": [
                    {
                        "jobTitle": "Software Engineer",
                        "companyName": "ACME",
                        "url": "https://example.com/1",
                        "pubDate": "2026-06-01T00:00:00Z",
                        "jobGeo": "Remote",
                        "jobDescription": "<p>An engineering role.</p>",
                    }
                ]
            }

    def get(*args, **kwargs):
        calls.append(kwargs["params"])
        return Response()

    monkeypatch.setattr(
        jobicy_source,
        "get_api_config",
        lambda: {"http": {"job_boards": {"jobicy": {"enabled": True}}}},
    )
    monkeypatch.setattr(jobicy_source.requests, "get", get)
    monkeypatch.setattr(jobicy_source, "_read_cache", lambda _geo: None)
    monkeypatch.setattr(jobicy_source, "_write_cache", lambda _geo, _jobs: None)

    jobs = jobicy_source.JobicySource().fetch(
        mk_params(["Software Engineer"], {"berlin": {"country": "DE", "location": "Berlin"}})
    )

    assert len(jobs) == 1
    assert calls[0]["geo"] == "germany"


def test_jobicy_skips_invalid_iso_geo(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "jobs": [
                    {
                        "jobTitle": "Software Engineer",
                        "companyName": "ACME",
                        "url": "https://example.com/1",
                        "pubDate": "2026-06-01T00:00:00Z",
                        "jobGeo": "Remote",
                        "jobDescription": "<p>An engineering role.</p>",
                    }
                ]
            }

    def get(*args, **kwargs):
        calls.append(kwargs["params"])
        return Response()

    monkeypatch.setattr(
        jobicy_source,
        "get_api_config",
        lambda: {"http": {"job_boards": {"jobicy": {"enabled": True}}}},
    )
    monkeypatch.setattr(jobicy_source.requests, "get", get)

    jobs = jobicy_source.JobicySource().fetch(
        mk_params(["Software Engineer"], {"sd": {"country": "SD", "location": "Khartoum"}})
    )

    assert jobs == []
    assert calls == []


def test_ats_url_helpers_cover_supported_platforms() -> None:
    cases = [
        (
            "https://boards.greenhouse.io/acme/jobs/123",
            "boards.greenhouse.io/acme",
            "Acme",
        ),
        (
            "https://job-boards.greenhouse.io/acme/jobs/123",
            "boards.greenhouse.io/acme",
            "Acme",
        ),
        (
            "https://jobs.lever.co/acme/00000000-0000-0000-0000-000000000000",
            "jobs.lever.co/acme",
            "Acme",
        ),
        (
            "https://jobs.ashbyhq.com/acme/00000000-0000-0000-0000-000000000000",
            "jobs.ashbyhq.com/acme",
            "Acme",
        ),
        (
            "https://jobs.smartrecruiters.com/acme/123",
            "jobs.smartrecruiters.com/acme",
            "Acme",
        ),
        ("https://apply.workable.com/acme/j/ABC123", "apply.workable.com/acme", "Acme"),
        ("https://acme.jobs.personio.de/job/123", "acme.jobs.personio.de", "Acme"),
        ("https://acme.recruitee.com/o/product-manager", "acme.recruitee.com", "Acme"),
        (
            "https://acme.teamtailor.com/jobs/123-product-manager",
            "acme.teamtailor.com",
            "Acme",
        ),
        (
            "https://acme.myworkdayjobs.com/External/job/Berlin/Product-Manager",
            "acme.myworkdayjobs.com/External",
            "Acme",
        ),
        (
            "https://acme.careers.hibob.com/jobs/00000000-0000-0000-0000-000000000000",
            "acme.careers.hibob.com",
            "Acme",
        ),
    ]

    for url, career_url, company in cases:
        assert extract_career_url(url) == career_url
        assert company_name_from_url(url) == company


def test_detect_ats_for_direct_scrapers() -> None:
    assert detect_ats("jobs.lever.co/acme") == ("lever", "acme")
    assert detect_ats("https://apply.workable.com/acme") == ("workable", "acme")
    assert detect_ats("https://acme.jobs.personio.de") == ("personio", "acme")
    assert detect_ats("https://acme.teamtailor.com/jobs") == ("teamtailor", "acme")
    assert detect_ats("https://acme.myworkdayjobs.com/External") == (
        "workday",
        "acme.myworkdayjobs.com/External",
    )
    assert detect_ats("https://example.com/careers") is None


def test_plain_429_search_error_uses_transient_failure_counter() -> None:
    provider = FakeProvider(exc=_quota_error(429, text="Too Many Requests"))
    search._reset_provider_failure(provider.name)

    router = search.SearchRouter(providers=[provider])

    assert router.search("product manager", {"country": "DE"}, count=1) == []
    assert search._provider_failure_count(provider.name) == 1
    search._reset_provider_failure(provider.name)


def test_adzuna_terminal_http_error_stops_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        adzuna_source,
        "get_api_config",
        lambda: {
            "http": {
                "job_boards": {"adzuna": {"enabled": True, "results_per_page": 50}},
                "jd_fetcher": {"max_description_chars": 4000},
            }
        },
    )
    calls = {"count": 0}

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        return ErrorResponse(402, reason="Payment Required")

    monkeypatch.setattr(adzuna_source.requests, "get", fake_get)
    regions = {"primary": {"country": "DE", "location": "Berlin"}}

    src = adzuna_source.AdzunaSource.__new__(adzuna_source.AdzunaSource)
    src._app_id = "app"
    src._api_key = "key"

    assert src.fetch(mk_params(["Product Manager", "Product Owner"], regions)) == []
    assert calls["count"] == 1


def test_strip_html_handles_escaped_greenhouse_html() -> None:
    text = utils.strip_html("&lt;p&gt;Own the roadmap&lt;/p&gt;<script>bad()</script>")

    assert text == "Own the roadmap"


def test_greenhouse_api_success_returns_job(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "title": "Senior Product Manager",
                "location": {"name": "Dubai"},
                "content": "<p>Responsibilities include product strategy and delivery.</p>",
            }

    monkeypatch.setattr(jd_fetcher, "_jd_config", lambda: {"max_description_chars": 4000})
    monkeypatch.setattr(jd_fetcher.requests, "get", lambda *args, **kwargs: Response())

    job = jd_fetcher.fetch_jd("https://job-boards.greenhouse.io/acme/jobs/123")

    assert job is not None
    assert job["title"] == "Senior Product Manager"
    assert job["source"] == "greenhouse_api"
    assert "product strategy" in job["snippet"]
    assert job["location"] == "Dubai"


def test_ashby_api_success_returns_job(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "jobPosting": {
                    "title": "Product Manager",
                    "locationName": "Berlin",
                    "descriptionHtml": "<p>Own discovery, delivery, and roadmap decisions.</p>",
                    "publishedAt": "2026-06-01T00:00:00.000Z",
                    "jobUrl": "https://jobs.ashbyhq.com/acme/job-123",
                }
            }

    monkeypatch.setattr(jd_fetcher, "_jd_config", lambda: {"max_description_chars": 4000})
    monkeypatch.setattr(jd_fetcher.requests, "get", lambda *args, **kwargs: Response())

    job = jd_fetcher.fetch_jd("https://jobs.ashbyhq.com/acme/job-123")

    assert job is not None
    assert job["title"] == "Product Manager"
    assert job["source"] == "ashby_api"
    assert job["location"] == "Berlin"
    assert job["posted_date_text"] == "2026-06-01"
    assert "roadmap decisions" in job["snippet"]


def test_ashby_api_runs_before_html_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "jobPosting": {
                    "title": "Product Owner",
                    "locationName": "Remote",
                    "descriptionHtml": "<p>Rendered through the API, not JavaScript.</p>",
                }
            }

    monkeypatch.setattr(jd_fetcher, "_jd_config", lambda: {"max_description_chars": 4000})
    monkeypatch.setattr(jd_fetcher.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(
        jd_fetcher,
        "_fetch_html",
        lambda *args, **kwargs: pytest.fail("HTML fetch should not run"),
    )

    job = jd_fetcher.fetch_jd("https://jobs.ashbyhq.com/acme/job-456")

    assert job is not None
    assert job["title"] == "Product Owner"
    assert "not JavaScript" in job["snippet"]


def test_lever_api_success_returns_job(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "text": "Product Manager",
                "hostedUrl": "https://jobs.lever.co/acme/00000000-0000-0000-0000-000000000000",
                "categories": {"location": "Berlin"},
                "descriptionPlain": "Responsibilities include discovery, delivery, and roadmap ownership.",
                "createdAt": 1780272000000,
            }

    monkeypatch.setattr(jd_fetcher, "_jd_config", lambda: {"max_description_chars": 4000})
    monkeypatch.setattr(jd_fetcher.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(
        jd_fetcher,
        "_fetch_html",
        lambda *args, **kwargs: pytest.fail("HTML fetch should not run"),
    )

    job = jd_fetcher.fetch_jd("https://jobs.lever.co/acme/00000000-0000-0000-0000-000000000000")

    assert job is not None
    assert job["source"] == "lever_api"
    assert job["location"] == "Berlin"
    assert "roadmap ownership" in job["snippet"]


def test_smartrecruiters_api_success_returns_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "name": "Product Manager",
                "releasedDate": "2026-06-01",
                "location": {"city": "Berlin", "country": "Germany"},
                "jobAd": {
                    "sections": [
                        {
                            "title": "Responsibilities",
                            "text": "<p>Own product strategy, delivery, and customer discovery.</p>",
                        }
                    ]
                },
            }

    monkeypatch.setattr(jd_fetcher, "_jd_config", lambda: {"max_description_chars": 4000})
    monkeypatch.setattr(jd_fetcher.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(
        jd_fetcher,
        "_fetch_html",
        lambda *args, **kwargs: pytest.fail("HTML fetch should not run"),
    )

    job = jd_fetcher.fetch_jd("https://jobs.smartrecruiters.com/acme/123-product-manager")

    assert job is not None
    assert job["source"] == "smartrecruiters_api"
    assert job["location"] == "Berlin, Germany"
    assert "customer discovery" in job["snippet"]


def test_workable_api_success_returns_job(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "title": "Product Manager",
                "published_on": "2026-06-01",
                "location": {"location": "Berlin"},
                "description": "<p>Requirements include product discovery and delivery experience.</p>",
            }

    monkeypatch.setattr(jd_fetcher, "_jd_config", lambda: {"max_description_chars": 4000})
    monkeypatch.setattr(jd_fetcher.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(
        jd_fetcher,
        "_fetch_html",
        lambda *args, **kwargs: pytest.fail("HTML fetch should not run"),
    )

    job = jd_fetcher.fetch_jd("https://apply.workable.com/acme/j/ABC123")

    assert job is not None
    assert job["source"] == "workable_api"
    assert job["location"] == "Berlin"
    assert "delivery experience" in job["snippet"]


def test_personio_api_success_returns_job(monkeypatch: pytest.MonkeyPatch) -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<workzag-jobs>
<position>
    <id>4242</id>
    <office>Munich</office>
    <additionalOffices><office>Berlin</office></additionalOffices>
    <name>Product Manager</name>
    <jobDescriptions>&lt;p&gt;Own roadmap and product discovery.&lt;/p&gt;</jobDescriptions>
    <createdAt>2026-06-01T00:00:00+00:00</createdAt>
</position>
</workzag-jobs>"""

    class Response:
        status_code = 200
        text = xml

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(jd_fetcher, "_jd_config", lambda: {"max_description_chars": 4000})
    monkeypatch.setattr(jd_fetcher.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(
        jd_fetcher,
        "_fetch_html",
        lambda *args, **kwargs: pytest.fail("HTML fetch should not run"),
    )

    job = jd_fetcher.fetch_jd("https://acme.jobs.personio.de/job/4242")

    assert job is not None
    assert job["source"] == "personio_api"
    assert job["title"] == "Product Manager"
    assert job["location"] == "Munich, Berlin"
    assert "product discovery" in job["snippet"]
    assert job["posted_date_text"] == "2026-06-01"


def test_recruitee_api_success_returns_job(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "offer": {
                    "title": "Product Manager",
                    "city": "Amsterdam",
                    "country": "Netherlands",
                    "description": "<p>Own the product roadmap and delivery.</p>",
                    "published_at": "2026-06-01T00:00:00Z",
                    "careers_url": "https://acme.recruitee.com/o/product-manager",
                }
            }

    monkeypatch.setattr(jd_fetcher, "_jd_config", lambda: {"max_description_chars": 4000})
    monkeypatch.setattr(jd_fetcher.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(
        jd_fetcher,
        "_fetch_html",
        lambda *args, **kwargs: pytest.fail("HTML fetch should not run"),
    )

    job = jd_fetcher.fetch_jd("https://acme.recruitee.com/o/product-manager")

    assert job is not None
    assert job["source"] == "recruitee_api"
    assert job["location"] == "Amsterdam, Netherlands"
    assert "product roadmap" in job["snippet"]


def test_breezy_api_success_returns_job(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> list:
            return [
                {
                    "friendly_id": "abc123-product-manager",
                    "name": "Product Manager",
                    "url": "https://acme.breezy.hr/p/abc123-product-manager",
                    "location": {"name": "Remote, US"},
                    "published_date": "2026-06-01T00:00:00Z",
                }
            ]

    monkeypatch.setattr(jd_fetcher, "_jd_config", lambda: {"max_description_chars": 4000})
    monkeypatch.setattr(jd_fetcher.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(
        jd_fetcher,
        "_fetch_html",
        lambda *args, **kwargs: pytest.fail("HTML fetch should not run"),
    )

    job = jd_fetcher.fetch_jd("https://acme.breezy.hr/p/abc123-product-manager")

    assert job is not None
    assert job["source"] == "breezy_api"
    assert job["title"] == "Product Manager"
    assert job["location"] == "Remote, US"


def test_teamtailor_api_success_returns_job(monkeypatch: pytest.MonkeyPatch) -> None:
    job_url = "https://acme.teamtailor.com/jobs/123-product-manager"

    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "items": [
                    {
                        "title": "Product Manager",
                        "url": job_url,
                        "content_html": "<p>fallback</p>",
                        "_jobposting": {
                            "description": "<p>Own the roadmap for our core platform.</p>",
                            "datePosted": "2026-06-01T00:00:00Z",
                            "hiringOrganization": {"name": "Acme"},
                            "jobLocation": [{"address": {"addressLocality": "Stockholm", "addressCountry": "SE"}}],
                        },
                    }
                ]
            }

    monkeypatch.setattr(jd_fetcher, "_jd_config", lambda: {"max_description_chars": 4000})
    monkeypatch.setattr(jd_fetcher.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(
        jd_fetcher,
        "_fetch_html",
        lambda *args, **kwargs: pytest.fail("HTML fetch should not run"),
    )

    job = jd_fetcher.fetch_jd(job_url)

    assert job is not None
    assert job["source"] == "teamtailor_api"
    assert job["company"] == "Acme"
    assert job["location"] == "Stockholm, SE"
    assert "roadmap for our core platform" in job["snippet"]


def test_workday_api_success_returns_job(monkeypatch: pytest.MonkeyPatch) -> None:
    job_url = "https://acme.wd12.myworkdayjobs.com/External_Career_Site/job/Berlin/Product-Manager_JR12345"

    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "jobPostingInfo": {
                    "title": "Product Manager",
                    "jobDescription": "<p>Own product strategy across the platform.</p>",
                    "location": "Berlin, Germany",
                    "startDate": "2026-06-01",
                }
            }

    monkeypatch.setattr(jd_fetcher, "_jd_config", lambda: {"max_description_chars": 4000})
    monkeypatch.setattr(jd_fetcher.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(
        jd_fetcher,
        "_fetch_html",
        lambda *args, **kwargs: pytest.fail("HTML fetch should not run"),
    )

    job = jd_fetcher.fetch_jd(job_url)

    assert job is not None
    assert job["source"] == "workday_api"
    assert job["location"] == "Berlin, Germany"
    assert "product strategy" in job["snippet"]


def test_greenhouse_api_falls_back_to_content_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def __init__(self, status_code: int, payload: dict) -> None:
            self.status_code = status_code
            self.payload = payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise jd_fetcher.requests.exceptions.HTTPError(response=self)

        def json(self) -> dict:
            return self.payload

    responses = [
        Response(404, {}),
        Response(
            200,
            {
                "jobs": [
                    {
                        "id": 123,
                        "title": "Product Manager",
                        "location": {"name": "Berlin"},
                        "content": "&lt;p&gt;Own product discovery and delivery.&lt;/p&gt;",
                        "updated_at": "2026-06-01T00:00:00Z",
                    }
                ]
            },
        ),
    ]

    monkeypatch.setattr(jd_fetcher, "_jd_config", lambda: {"max_description_chars": 4000})
    monkeypatch.setattr(jd_fetcher.requests, "get", lambda *args, **kwargs: responses.pop(0))

    job = jd_fetcher.fetch_jd("https://boards.greenhouse.io/acme/jobs/123")

    assert job is not None
    assert job["title"] == "Product Manager"
    assert job["posted_date_text"] == "2026-06-01"
    assert "Own product discovery" in job["snippet"]


def test_greenhouse_api_repairs_stale_direct_id_with_exact_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def __init__(self, status_code: int, payload: dict) -> None:
            self.status_code = status_code
            self.payload = payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise jd_fetcher.requests.exceptions.HTTPError(response=self)

        def json(self) -> dict:
            return self.payload

    responses = [
        Response(404, {}),
        Response(
            200,
            {
                "jobs": [
                    {
                        "id": 456,
                        "title": "Product Owner",
                        "location": {"name": "Belfast"},
                        "content": "<p>Own discovery, delivery, and stakeholder alignment.</p>",
                        "absolute_url": "https://job-boards.eu.greenhouse.io/acme/jobs/456",
                    }
                ]
            },
        ),
    ]

    monkeypatch.setattr(jd_fetcher, "_jd_config", lambda: {"max_description_chars": 4000})
    monkeypatch.setattr(jd_fetcher.requests, "get", lambda *args, **kwargs: responses.pop(0))

    job = jd_fetcher.fetch_jd(
        "https://boards.greenhouse.io/acme/jobs/123",
        expected_title="Job Application for Product Owner at Acme",
    )

    assert job is not None
    assert job["title"] == "Product Owner"
    assert job["url"] == "https://job-boards.eu.greenhouse.io/acme/jobs/456"
    assert "stakeholder alignment" in job["snippet"]


def test_greenhouse_api_does_not_repair_to_generic_product_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        def __init__(self, status_code: int, payload: dict) -> None:
            self.status_code = status_code
            self.payload = payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise jd_fetcher.requests.exceptions.HTTPError(response=self)

        def json(self) -> dict:
            return self.payload

    responses = [
        Response(404, {}),
        Response(
            200,
            {
                "jobs": [
                    {
                        "id": 456,
                        "title": "Product Marketing Manager",
                        "location": {"name": "Tel Aviv"},
                        "content": "<p>Marketing role.</p>",
                    }
                ]
            },
        ),
    ]

    monkeypatch.setattr(jd_fetcher, "_jd_config", lambda: {"min_text_length": 300})
    monkeypatch.setattr(jd_fetcher.requests, "get", lambda *args, **kwargs: responses.pop(0))
    monkeypatch.setattr(jd_fetcher, "_fetch_html", lambda *args, **kwargs: (None, 404))
    job = jd_fetcher.fetch_jd(
        "https://boards.greenhouse.io/acme/jobs/123",
        expected_title="Product Manager",
    )

    assert job is None


def test_greenhouse_listing_text_fallback_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        jd_fetcher,
        "_jd_config",
        lambda: {"min_text_length": 300, "max_description_chars": 4000},
    )
    monkeypatch.setattr(jd_fetcher, "_fetch_greenhouse_api", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        jd_fetcher,
        "_fetch_html",
        lambda *args, **kwargs: (
            "Jobs at Scale AI Current openings at Scale AI Create a Job Alert "
            "Search Department Select Office Select 167 jobs",
            200,
        ),
    )

    job = jd_fetcher.fetch_jd(
        "https://job-boards.greenhouse.io/scaleai/jobs/4609736005",
        expected_title="AI Product Manager",
    )

    assert job is None


def test_greenhouse_403_is_browser_fetchable_not_dead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Response:
        status_code = 403

    monkeypatch.setattr(utils.requests, "head", lambda *args, **kwargs: Response())

    assert utils.url_is_alive("https://boards.greenhouse.io/acme/jobs/123")


def test_greenhouse_discovery_enriches_generic_search_snippet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Router:
        def search(self, query: str, region_config: dict, count: int = 10) -> list[search.SearchResult]:
            return [
                search.SearchResult(
                    url="https://boards.greenhouse.io/acme/jobs/123",
                    title="Jobs at Acme",
                    description="Current openings at Acme Create a Job Alert",
                    source="SearXNG",
                )
            ]

    monkeypatch.setattr(
        _ats_mod,
        "_enrich_ats_discovery_job",
        lambda _url: {
            "title": "Product Manager",
            "company": "Acme",
            "location": "Berlin",
            "url": "https://boards.greenhouse.io/acme/jobs/123",
            "posted_date_text": "2026-06-01",
            "snippet": "Product Manager\nBerlin\n\nOwn the roadmap and customer discovery.",
        },
    )

    jobs = search._discover_region(
        "primary",
        {"location": "Berlin"},
        ["Product Manager"],
        ["greenhouse"],
        Router(),
        max_results_per_query=10,
        max_queries_per_region=0,
        ats_detail_timeout=8,
    )

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Product Manager"
    assert "Own the roadmap" in jobs[0]["snippet"]
    assert jobs[0]["source"] == "SearXNG ATS discovery: greenhouse API"


def test_non_greenhouse_discovery_uses_direct_ats_enrichment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Router:
        def search(self, query: str, region_config: dict, count: int = 10) -> list[search.SearchResult]:
            return [
                search.SearchResult(
                    url="https://jobs.smartrecruiters.com/acme/123-product-manager",
                    title="Product Manager",
                    description="Short search summary",
                    source="SearXNG",
                )
            ]

    monkeypatch.setattr(
        _ats_mod,
        "_enrich_ats_discovery_job",
        lambda _url: {
            "title": "Product Manager",
            "company": "Acme",
            "location": "Berlin",
            "url": "https://jobs.smartrecruiters.com/acme/123-product-manager",
            "posted_date_text": "2026-06-01",
            "snippet": "Product Manager\nBerlin\n\nResponsibilities include roadmap ownership and delivery.",
        },
    )

    jobs = search._discover_region(
        "primary",
        {"location": "Berlin"},
        ["Product Manager"],
        ["smartrecruiters"],
        Router(),
        max_results_per_query=10,
        max_queries_per_region=0,
        ats_detail_timeout=8,
    )

    assert len(jobs) == 1
    assert jobs[0]["source"] == "SearXNG ATS discovery: smartrecruiters API"
    assert "roadmap ownership" in jobs[0]["snippet"]


def test_ats_discovery_search_config_override_removes_api_query_cap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    class Router:
        def search(self, query: str, region_config: dict, count: int = 10) -> list[search.SearchResult]:
            job_id = "123" if "Product Manager" in query else "456"
            return [
                search.SearchResult(
                    url=f"https://boards.greenhouse.io/acme/jobs/{job_id}",
                    title="Product Manager",
                    description="Responsibilities include product discovery.",
                    source="SearXNG",
                )
            ]

    monkeypatch.setattr(
        _ats_mod,
        "_search_config",
        lambda: {
            "ats_discovery": {
                "enabled": True,
                "sources": ["greenhouse"],
                "results_per_query": 10,
                "max_queries_per_region": 1,
            }
        },
    )
    monkeypatch.setattr(_ats_mod, "SearchRouter", lambda *_args, **_kwargs: Router())
    monkeypatch.setattr(_ats_mod, "all_providers_exhausted", lambda *_a, **_k: False)
    monkeypatch.setattr(_ats_mod, "_enrich_ats_discovery_job", lambda _url: None)
    monkeypatch.setattr(_ats_mod, "_ats_location_matches_policy", lambda *_args, **_kwargs: True)

    jobs = search.discover_ats_jobs_by_search(
        ["Product Manager", "Product Owner"],
        {"primary": {"location": "Berlin"}},
        ats_discovery_config={"max_queries_per_region": 0},
    )

    assert [job["url"] for job in jobs] == [
        "https://boards.greenhouse.io/acme/jobs/123",
        "https://boards.greenhouse.io/acme/jobs/456",
    ]


def test_discover_ats_jobs_by_search_issues_one_pass_per_hunt_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A region with hunt_languages: [en, de] must be searched in both — not just
    the first configured language (the pre-consolidation default_search_lang bug)."""
    seen_langs: list[str] = []

    class Router:
        def search(self, query: str, region_config: dict, count: int = 10) -> list[search.SearchResult]:
            seen_langs.append(region_config.get("search_lang"))
            return []

    monkeypatch.setattr(
        _ats_mod,
        "_search_config",
        lambda: {"ats_discovery": {"enabled": True, "sources": ["greenhouse"], "results_per_query": 10}},
    )
    monkeypatch.setattr(_ats_mod, "SearchRouter", lambda *_args, **_kwargs: Router())
    monkeypatch.setattr(_ats_mod, "all_providers_exhausted", lambda *_a, **_k: False)

    search.discover_ats_jobs_by_search(
        ["Product Manager"],
        {"primary": {"location": "Berlin"}},
        hunt_languages=["en", "de"],
    )

    assert "en" in seen_langs
    assert "de" in seen_langs


# ---------------------------------------------------------------------------
# Task 3: API-exhausted and no-key fallback health
# ---------------------------------------------------------------------------


def test_search_router_health_exhausted_provider_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exhausted provider should appear in health.exhausted_providers."""
    provider = FakeProvider(exc=AssertionError("Exhausted provider should not be called"))
    monkeypatch.setattr(_router_mod._PROVIDER_STATE, "run_disabled", {provider.name})

    results, health = search.SearchRouter(providers=[provider]).search_with_health(
        "product manager", {"country": "DE"}, count=1
    )

    assert results == []
    assert provider.calls == 0
    assert provider.name in health.exhausted_providers
    assert provider.name not in health.transient_failures


def test_search_router_health_no_key_provider_skipped() -> None:
    """A provider with no API key should appear in health.skipped_no_key."""
    provider = FakeProvider(enabled=False)

    results, health = search.SearchRouter(providers=[provider]).search_with_health("product manager", {}, count=1)

    assert results == []
    assert provider.calls == 0
    assert provider.name in health.skipped_no_key
    assert provider.name not in health.exhausted_providers


def test_search_router_health_transient_failure_recorded() -> None:
    """A transient HTTP failure should appear in health.transient_failures."""
    provider = FakeProvider(exc=_quota_error(500, text="Internal Server Error"))
    search._reset_provider_failure(provider.name)

    results, health = search.SearchRouter(providers=[provider]).search_with_health(
        "product manager", {"country": "DE"}, count=1
    )

    assert results == []
    assert provider.name in health.transient_failures
    assert provider.name not in health.exhausted_providers
    search._reset_provider_failure(provider.name)


def test_search_router_health_successful_provider_in_providers_used() -> None:
    """A provider that returns results should appear in health.providers_used."""
    provider = FakeProvider(
        name="fake_no_key",
        results=[
            search.SearchResult(
                url="https://example.com/job/1",
                title="Product Manager",
                description="Own the roadmap.",
                source="fake",
            )
        ],
    )

    results, health = search.SearchRouter(providers=[provider]).search_with_health("product manager", {}, count=1)

    assert len(results) == 1
    assert "fake_no_key" in health.providers_used


def test_later_provider_runs_when_earlier_providers_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exhausted providers are skipped without a call; the next provider in order still runs."""
    exhausted_a = FakeProvider(name="exhausted_a", exc=AssertionError("should not be called"))
    exhausted_b = FakeProvider(name="exhausted_b", exc=AssertionError("should not be called"))
    working = FakeProvider(
        name="searxng",
        results=[
            search.SearchResult(
                url="https://jobs.lever.co/co/abc",
                title="Product Manager",
                description="Role.",
                source="SearXNG",
            )
        ],
    )
    monkeypatch.setattr(_router_mod._PROVIDER_STATE, "run_disabled", {"exhausted_a", "exhausted_b"})

    router = search.SearchRouter(providers=[exhausted_a, exhausted_b, working])
    results, health = router.search_with_health("product manager", {}, count=5)

    assert len(results) == 1
    assert working.calls == 1
    assert exhausted_a.calls == 0
    assert "exhausted_a" in health.exhausted_providers
    assert "exhausted_b" in health.exhausted_providers
    assert "searxng" in health.providers_used


# ---------------------------------------------------------------------------
# Task 6: career-page source handling
# ---------------------------------------------------------------------------


def test_career_pages_detect_ats_from_url() -> None:
    from job_hunter.sources.career_pages import detect_ats_from_url

    result = detect_ats_from_url("https://jobs.lever.co/acme")
    assert result is not None
    platform, slug = result
    assert platform == "lever"
    assert slug == "acme"


def test_career_pages_detect_ats_returns_none_for_custom_url() -> None:
    from job_hunter.sources.career_pages import detect_ats_from_url

    assert detect_ats_from_url("https://example.com/careers") is None


def test_career_pages_extract_jsonld_jobs_from_html() -> None:
    from job_hunter.sources.career_pages import extract_jsonld_jobs

    html = """<html><head>
    <script type="application/ld+json">
    {"@type": "JobPosting", "title": "Product Manager", "url": "https://example.com/jobs/1",
     "datePosted": "2026-06-01", "description": "<p>Own roadmap and delivery.</p>"}
    </script>
    </head></html>"""

    jobs = extract_jsonld_jobs(html, "https://example.com", "ExampleCo", ["Product Manager"])
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Product Manager"
    assert jobs[0]["extraction_method"] == "jsonld"
    assert "roadmap" in jobs[0]["snippet"]


def test_career_pages_extract_jsonld_jobs_filters_by_title() -> None:
    from job_hunter.sources.career_pages import extract_jsonld_jobs

    html = """<html><head>
    <script type="application/ld+json">
    {"@type": "JobPosting", "title": "Software Engineer", "url": "https://example.com/jobs/2",
     "description": "Engineering role."}
    </script>
    </head></html>"""

    jobs = extract_jsonld_jobs(html, "https://example.com", "ExampleCo", ["Product Manager"])
    assert jobs == []


def test_career_pages_extract_jsonld_graph_form() -> None:
    from job_hunter.sources.career_pages import extract_jsonld_jobs

    html = """<html><head>
    <script type="application/ld+json">
    {"@context": "https://schema.org", "@graph": [
      {"@type": "JobPosting", "title": "Product Owner", "url": "https://example.com/jobs/3",
       "description": "Own delivery."}
    ]}
    </script>
    </head></html>"""

    jobs = extract_jsonld_jobs(html, "https://example.com", "ExampleCo", ["Product Owner"])
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Product Owner"


def test_career_pages_no_search_provider_custom_page_ingestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """extract_career_page_jobs should work without any search provider."""
    from job_hunter.sources import career_pages

    html_with_jsonld = """<html><head>
    <script type="application/ld+json">
    {"@type": "JobPosting", "title": "Product Manager",
     "url": "https://custom.example.com/jobs/42",
     "description": "<p>Lead product delivery and discovery.</p>"}
    </script>
    </head></html>"""

    monkeypatch.setattr(
        career_pages,
        "detect_ats_from_url",
        lambda _url: None,
    )
    monkeypatch.setattr(
        career_pages,
        "_fetch_html_safe",
        lambda _url: (html_with_jsonld, 200),
    )

    jobs = career_pages.extract_career_page_jobs(
        {"name": "CustomCo", "career_url": "https://custom.example.com/careers"},
        ["Product Manager"],
    )

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Product Manager"
    assert jobs[0]["extraction_method"] == "jsonld"


def test_career_pages_falls_back_to_playwright_after_cheap_rungs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from job_hunter.sources import career_pages

    monkeypatch.setattr(career_pages, "detect_ats_from_url", lambda _url: None)
    monkeypatch.setattr(career_pages, "_fetch_html_safe", lambda _url: ("<html></html>", 200))
    monkeypatch.setattr(career_pages, "_try_sitemap_discovery", lambda *args: [])
    monkeypatch.setattr(career_pages, "_try_static_html", lambda *args: [])
    monkeypatch.setattr(
        career_pages,
        "_try_playwright",
        lambda *args: [{"title": "Product Owner", "url": "https://example.com/jobs/2"}],
    )

    jobs = career_pages.extract_career_page_jobs(
        {"name": "CloudCo", "career_url": "https://cloud.example.com/careers"},
        ["Product Owner"],
    )

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Product Owner"


# ---------------------------------------------------------------------------
# 04-04: Search exhaustion detection + ATS-only fallback (paid repo)
# ---------------------------------------------------------------------------

_sp = search


def _reset_exhaustion_state() -> None:
    """Reset module-level exhaustion counters to defaults after each test."""
    _sp._PROVIDER_STATE.searxng_consecutive_zeros = 0
    _sp._PROVIDER_STATE.ats_only_logged = False


def test_all_providers_exhausted_returns_false_with_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Returns False when an ATS discovery provider is available."""
    monkeypatch.setattr(_router_mod._PROVIDER_STATE, "run_disabled", set())
    monkeypatch.setattr(_sp.SearxngProvider, "enabled", lambda self: True)
    _sp._PROVIDER_STATE.searxng_consecutive_zeros = 0

    result = _sp.all_providers_exhausted()

    assert result is False
    _reset_exhaustion_state()


def test_all_providers_exhausted_returns_true_when_all_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Returns True when ATS discovery providers are unavailable."""
    monkeypatch.setattr(_router_mod._PROVIDER_STATE, "run_disabled", set())
    monkeypatch.setattr(_sp.SearxngProvider, "enabled", lambda self: False)

    result = _sp.all_providers_exhausted()

    assert result is True
    _reset_exhaustion_state()


def test_discover_ats_jobs_by_search_returns_empty_when_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """discover_ats_jobs_by_search returns [] immediately when all providers exhausted."""
    monkeypatch.setattr(_sp, "all_providers_exhausted", lambda *_a, **_k: True)

    result = _sp.discover_ats_jobs_by_search(
        ["Software Engineer"],
        {"EU": {"location": "Europe"}},
    )

    assert result == []
    _reset_exhaustion_state()


def test_searxng_uses_configured_engines_without_zero_penalty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty SearXNG results should not globally mark the provider as unavailable."""
    _sp._PROVIDER_STATE.searxng_consecutive_zeros = 0
    calls: list[dict] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"results": []}

    def fake_get(*args, **kwargs):
        calls.append(kwargs["params"])
        return FakeResponse()

    monkeypatch.setattr(_sp.requests, "get", fake_get)
    monkeypatch.setattr(_sp, "_timeout", lambda _section: 15)
    provider = _sp.SearxngProvider(
        {
            "searxng_base_url": "http://localhost:8080",
            "searxng_categories": "general",
            "searxng_engines": ["bing", "duckduckgo", "brave"],
        }
    )
    provider.search("test", {})

    assert _sp._PROVIDER_STATE.searxng_consecutive_zeros == 0
    assert calls[0]["categories"] == "general"
    assert calls[0]["engines"] == "bing,duckduckgo,brave"
    _reset_exhaustion_state()


def test_ats_search_queries_split_grouped_site_queries() -> None:
    # "Data Analyst" doesn't trigger any title-variant rule, keeping this test
    # focused on its stated purpose: splitting a grouped `site:X OR site:Y` query.
    queries = _sp._ats_search_queries(
        "site:boards.greenhouse.io OR site:job-boards.greenhouse.io",
        "Data Analyst",
        "Berlin",
    )

    assert queries == [
        'site:boards.greenhouse.io "Data Analyst" "Berlin"',
        'site:boards.greenhouse.io "Data Analyst"',
        'site:job-boards.greenhouse.io "Data Analyst" "Berlin"',
        'site:job-boards.greenhouse.io "Data Analyst"',
    ]
