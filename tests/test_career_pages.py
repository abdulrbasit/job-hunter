"""Tests for sources/career_pages.py — no real HTTP calls."""

from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

from job_hunter.sources import career_pages

# ── detect_ats() ─────────────────────────────────────────────────────────────


def test_detect_ats_greenhouse() -> None:
    ats, slug, template = career_pages.detect_ats("https://boards.greenhouse.io/deliveryhero")
    assert ats == "greenhouse"
    assert slug == "deliveryhero"
    assert "greenhouse" in template


def test_detect_ats_lever() -> None:
    ats, slug, template = career_pages.detect_ats("https://jobs.lever.co/getyourguide")
    assert ats == "lever"
    assert slug == "getyourguide"


def test_detect_ats_ashby() -> None:
    ats, slug, _ = career_pages.detect_ats("https://jobs.ashbyhq.com/stripe/abc-uuid")
    assert ats == "ashby"
    assert slug == "stripe"


def test_detect_ats_teamtailor() -> None:
    ats, slug, template = career_pages.detect_ats("https://acme.teamtailor.com/jobs")
    assert ats == "teamtailor"
    assert slug == "acme"
    # Teamtailor has no public JSON API; template is empty string
    assert template == ""


def test_detect_ats_unknown_returns_empty() -> None:
    ats, slug, template = career_pages.detect_ats("https://careers.customcompany.com/jobs")
    assert ats == ""
    assert slug == ""
    assert template == ""


def test_detect_ats_workday() -> None:
    ats, slug, template = career_pages.detect_ats("https://acme.myworkdayjobs.com/en-US/External")
    assert ats == "workday"
    assert slug == "acme"


# ── extract_jsonld_jobs() ─────────────────────────────────────────────────────


_JSONLD_HTML = """
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org/",
  "@type": "JobPosting",
  "title": "Product Manager",
  "datePosted": "2026-06-01",
  "hiringOrganization": {"@type": "Organization", "name": "TestCorp"},
  "jobLocation": {"@type": "Place", "address": {"addressLocality": "Berlin"}},
  "description": "We are looking for a PM to join our team.",
  "apply": {"url": "https://jobs.testcorp.com/apply/pm-123"}
}
</script>
</head>
<body><h1>Product Manager</h1></body>
</html>
"""

_JSONLD_LIST_HTML = """
<html>
<head>
<script type="application/ld+json">
[
  {
    "@type": "JobPosting",
    "title": "Senior Product Manager",
    "apply": {"url": "https://jobs.testcorp.com/apply/spm-456"}
  },
  {
    "@type": "JobPosting",
    "title": "Product Owner",
    "apply": {"url": "https://jobs.testcorp.com/apply/po-789"}
  }
]
</script>
</head>
<body></body>
</html>
"""

_NO_JSONLD_HTML = """
<html>
<head><title>Careers</title></head>
<body><a href="/jobs/pm-1">Product Manager</a></body>
</html>
"""


def test_extract_jsonld_jobs_finds_single_posting() -> None:
    jobs = career_pages.extract_jsonld_jobs(_JSONLD_HTML, "https://careers.testcorp.com", "TestCorp")
    assert len(jobs) == 1
    job = jobs[0]
    assert job["title"] == "Product Manager"
    assert job["company"] == "TestCorp"
    assert job["location"] == "Berlin"
    assert job["extraction_method"] == "jsonld"
    assert job["url"] == "https://jobs.testcorp.com/apply/pm-123"


def test_extract_jsonld_jobs_finds_list_of_postings() -> None:
    jobs = career_pages.extract_jsonld_jobs(_JSONLD_LIST_HTML, "https://careers.testcorp.com", "TestCorp")
    assert len(jobs) == 2
    titles = {j["title"] for j in jobs}
    assert "Senior Product Manager" in titles
    assert "Product Owner" in titles


def test_extract_jsonld_jobs_returns_empty_when_none_present() -> None:
    jobs = career_pages.extract_jsonld_jobs(_NO_JSONLD_HTML, "https://careers.testcorp.com", "TestCorp")
    assert jobs == []


def test_extract_jsonld_jobs_deduplicates_same_apply_url() -> None:
    html = """
    <html>
    <head>
    <script type="application/ld+json">{"@type": "JobPosting", "title": "PM", "apply": {"url": "https://example.com/pm"}}</script>
    <script type="application/ld+json">{"@type": "JobPosting", "title": "PM duplicate", "apply": {"url": "https://example.com/pm"}}</script>
    </head>
    </html>
    """
    jobs = career_pages.extract_jsonld_jobs(html, "https://example.com", "Co")
    assert len(jobs) == 1


def test_extract_jsonld_jobs_preserves_raw_schema_org() -> None:
    jobs = career_pages.extract_jsonld_jobs(_JSONLD_HTML, "https://careers.testcorp.com", "TestCorp")
    assert "raw_schema_org" in jobs[0]
    assert jobs[0]["raw_schema_org"]["@type"] == "JobPosting"


# ── extract_career_page_jobs() — ATS endpoint rung ───────────────────────────


def test_extract_career_page_jobs_uses_ats_api_for_greenhouse_url() -> None:
    """When the career_url is a Greenhouse board URL, the ladder uses the ATS API endpoint."""
    company = {
        "name": "TestCo",
        "career_url": "boards.greenhouse.io/testco",
        "location": "Berlin",
    }
    fake_api_response = {
        "jobs": [
            {
                "title": "Product Manager",
                "absolute_url": "https://boards.greenhouse.io/testco/jobs/12345",
                "location": {"name": "Berlin"},
                "updated_at": "2026-06-01",
                "content": "Join our team.",
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = fake_api_response

    with patch("job_hunter.sources.career_pages.requests.get", return_value=mock_resp):
        jobs = career_pages.extract_career_page_jobs(
            company,
            title_filters=["Product Manager"],
        )

    assert len(jobs) == 1
    assert jobs[0]["extraction_method"] == "ats_api"
    assert jobs[0]["detected_ats"] == "greenhouse"
    assert jobs[0]["title"] == "Product Manager"


def test_extract_career_page_jobs_falls_through_to_jsonld_when_ats_api_empty() -> None:
    """When the ATS API returns no jobs, the ladder moves to JSON-LD extraction."""
    company = {
        "name": "TestCo",
        "career_url": "boards.greenhouse.io/testco",
        "location": "Berlin",
    }

    html_with_jsonld = """
    <html>
    <head>
    <script type="application/ld+json">
    {"@type": "JobPosting", "title": "Product Owner",
     "apply": {"url": "https://boards.greenhouse.io/testco/jobs/99999"}}
    </script>
    </head>
    </html>
    """

    api_response = MagicMock()
    api_response.raise_for_status = MagicMock()
    api_response.json.return_value = {"jobs": []}  # empty ATS response

    html_response = MagicMock()
    html_response.raise_for_status = MagicMock()
    html_response.text = html_with_jsonld
    html_response.url = "https://boards.greenhouse.io/testco"

    call_count = []

    def fake_get(url, **kwargs):
        call_count.append(url)
        if urlparse(url).hostname == "boards-api.greenhouse.io":
            return api_response
        return html_response

    with patch("job_hunter.sources.career_pages.requests.get", side_effect=fake_get):
        jobs = career_pages.extract_career_page_jobs(
            company,
            title_filters=["Product Owner"],
        )

    assert len(jobs) == 1
    assert jobs[0]["extraction_method"] == "jsonld"
    assert jobs[0]["title"] == "Product Owner"


def test_extract_career_page_jobs_no_search_provider_called() -> None:
    """extract_career_page_jobs must never import or call any search provider."""
    company = {
        "name": "CustomCo",
        "career_url": "https://careers.customco.com",
        "location": "Berlin",
    }

    html_with_link = """
    <html>
    <body>
    <a href="/jobs/product-manager-berlin">Product Manager - Berlin</a>
    </body>
    </html>
    """

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = html_with_link
    mock_resp.url = "https://careers.customco.com"

    mock_head = MagicMock()
    mock_head.ok = False

    with (
        patch("job_hunter.sources.career_pages.requests.get", return_value=mock_resp),
        patch("job_hunter.sources.career_pages.requests.head", return_value=mock_head),
        patch("job_hunter.sources.search.SearchRouter.search") as mock_search,
    ):
        career_pages.extract_career_page_jobs(
            company,
            title_filters=["Product Manager"],
        )

    mock_search.assert_not_called()


def test_extract_career_page_jobs_uses_lightpanda_before_playwright() -> None:
    company = {
        "name": "LightCo",
        "career_url": "https://careers.lightco.example",
        "location": "Berlin",
    }

    with (
        patch("job_hunter.sources.career_pages.detect_ats_from_url", return_value=None),
        patch(
            "job_hunter.sources.career_pages._fetch_html_safe",
            return_value=("<html></html>", 200),
        ),
        patch("job_hunter.sources.career_pages._try_sitemap_discovery", return_value=[]),
        patch("job_hunter.sources.career_pages._try_static_html", return_value=[]),
        patch(
            "job_hunter.sources.career_pages.fetch_lightpanda_career_jobs",
            return_value=[{"title": "Product Manager", "url": "https://example.com/jobs/1"}],
        ),
        patch("job_hunter.sources.career_pages._try_playwright") as mock_pw,
    ):
        jobs = career_pages.extract_career_page_jobs(company, ["Product Manager"])

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Product Manager"
    mock_pw.assert_not_called()


def test_extract_career_page_jobs_uses_firecrawl_after_local_fallbacks() -> None:
    company = {
        "name": "CloudCo",
        "career_url": "https://careers.cloudco.example",
        "location": "Berlin",
    }

    with (
        patch("job_hunter.sources.career_pages.detect_ats_from_url", return_value=None),
        patch(
            "job_hunter.sources.career_pages._fetch_html_safe",
            return_value=("<html></html>", 200),
        ),
        patch("job_hunter.sources.career_pages._try_sitemap_discovery", return_value=[]),
        patch("job_hunter.sources.career_pages._try_static_html", return_value=[]),
        patch("job_hunter.sources.career_pages.fetch_lightpanda_career_jobs", return_value=[]),
        patch("job_hunter.sources.career_pages._try_playwright", return_value=[]),
        patch(
            "job_hunter.sources.career_pages.fetch_firecrawl_career_jobs",
            return_value=[{"title": "Product Owner", "url": "https://example.com/jobs/2"}],
        ),
    ):
        jobs = career_pages.extract_career_page_jobs(company, ["Product Owner"])

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Product Owner"
