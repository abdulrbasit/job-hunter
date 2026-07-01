"""Tests for sources/ats.py — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

from job_hunter.sources import ats


def _make_response(json_data=None, text=None, status=200, raise_error=False):
    resp = MagicMock()
    resp.status_code = status
    if raise_error:
        resp.raise_for_status.side_effect = Exception(str(status))
    else:
        resp.raise_for_status = MagicMock()
    if json_data is not None:
        resp.json.return_value = json_data
    if text is not None:
        resp.text = text
    return resp


# Aliases kept for the two call-site styles used throughout the file.
def _mock_get(json_data, status=200):
    return _make_response(json_data=json_data, status=status)


def _mock_post(json_data, status=200):
    return _make_response(json_data=json_data, status=status)


# ── detect_ats() ─────────────────────────────────────────────────────────────


def test_detect_greenhouse() -> None:
    assert ats.detect_ats("boards.greenhouse.io/deliveryhero") == ("greenhouse", "deliveryhero")


def test_detect_greenhouse_with_https() -> None:
    assert ats.detect_ats("https://boards.greenhouse.io/traderepublic") == (
        "greenhouse",
        "traderepublic",
    )


def test_detect_lever() -> None:
    assert ats.detect_ats("jobs.lever.co/getyourguide") == ("lever", "getyourguide")


def test_detect_smartrecruiters() -> None:
    assert ats.detect_ats("jobs.smartrecruiters.com/Scout24") == ("smartrecruiters", "Scout24")


def test_detect_workable() -> None:
    assert ats.detect_ats("apply.workable.com/mycompany") == ("workable", "mycompany")


def test_detect_job_boards_greenhouse() -> None:
    assert ats.detect_ats("job-boards.greenhouse.io/contentful") == ("greenhouse", "contentful")


def test_detect_ashby() -> None:
    assert ats.detect_ats("jobs.ashbyhq.com/mycompany") == ("ashby", "mycompany")


def test_detect_hibob() -> None:
    assert ats.detect_ats("kleinanzeigendegmbh.careers.hibob.com") == (
        "hibob",
        "kleinanzeigendegmbh",
    )


def test_detect_hibob_with_https() -> None:
    assert ats.detect_ats("https://kleinanzeigendegmbh.careers.hibob.com") == (
        "hibob",
        "kleinanzeigendegmbh",
    )


def test_detect_unknown_returns_none() -> None:
    assert ats.detect_ats("jobs.personio.com") is None


def test_detect_direct_career_page_returns_none() -> None:
    assert ats.detect_ats("careers.soundcloud.com") is None


def test_detect_subdirectory_greenhouse_extracts_company_slug() -> None:
    # detect_ats now uses ats_urls which correctly extracts the company slug
    # from job posting URLs (stops at the first path segment)
    result = ats.detect_ats("boards.greenhouse.io/company/jobs/12345")
    assert result == ("greenhouse", "company")


# ── fetch_greenhouse_jobs() ──────────────────────────────────────────────────

GH_RESPONSE = {
    "jobs": [
        {
            "title": "Product Manager Berlin",
            "location": {"name": "Berlin, Germany"},
            "absolute_url": "https://boards.greenhouse.io/deliveryhero/jobs/12345",
            "content": "<p>Great PM role in Berlin.</p>",
            "updated_at": "2026-04-01T10:00:00Z",
        },
        {
            "title": "Product Manager San Francisco",
            "location": {"name": "San Francisco, CA"},
            "absolute_url": "https://boards.greenhouse.io/deliveryhero/jobs/99999",
            "content": "<p>US-based role.</p>",
            "updated_at": "2026-04-01T10:00:00Z",
        },
    ]
}


def test_greenhouse_filters_by_location() -> None:
    with patch("job_hunter.sources.ats.requests.get", return_value=_mock_get(GH_RESPONSE)):
        jobs = ats.fetch_greenhouse_jobs("deliveryhero", "Delivery Hero", "Berlin", [])
    assert len(jobs) == 1
    assert "San Francisco" not in jobs[0]["title"]


def test_greenhouse_filters_by_title() -> None:
    with patch("job_hunter.sources.ats.requests.get", return_value=_mock_get(GH_RESPONSE)):
        jobs = ats.fetch_greenhouse_jobs("deliveryhero", "Delivery Hero", "Berlin", ["Product Owner"])
    assert len(jobs) == 0


def test_greenhouse_returns_correct_fields() -> None:
    with patch("job_hunter.sources.ats.requests.get", return_value=_mock_get(GH_RESPONSE)):
        jobs = ats.fetch_greenhouse_jobs("deliveryhero", "Delivery Hero", "Berlin", [])
    job = jobs[0]
    assert job["source"] == "Greenhouse API"
    assert job["company"] == "Delivery Hero"
    assert job["url"] == "https://boards.greenhouse.io/deliveryhero/jobs/12345"
    assert job["posted_date_text"] == "2026-04-01"
    assert "Berlin" in job["snippet"]


def test_greenhouse_strips_html_from_snippet() -> None:
    with patch("job_hunter.sources.ats.requests.get", return_value=_mock_get(GH_RESPONSE)):
        jobs = ats.fetch_greenhouse_jobs("deliveryhero", "Delivery Hero", "Berlin", [])
    assert "<p>" not in jobs[0]["snippet"]


def test_greenhouse_returns_empty_on_api_error() -> None:
    with patch("job_hunter.sources.ats.requests.get", side_effect=Exception("timeout")):
        jobs = ats.fetch_greenhouse_jobs("deliveryhero", "Delivery Hero", "Berlin", [])
    assert jobs == []


def test_greenhouse_no_location_filter_returns_all() -> None:
    with patch("job_hunter.sources.ats.requests.get", return_value=_mock_get(GH_RESPONSE)):
        jobs = ats.fetch_greenhouse_jobs("deliveryhero", "Delivery Hero", "", [])
    assert len(jobs) == 2


# ── fetch_lever_jobs() ───────────────────────────────────────────────────────

LEVER_RESPONSE = [
    {
        "text": "Product Owner",
        "categories": {"location": "Berlin, Germany", "allLocations": ["Berlin, Germany"]},
        "hostedUrl": "https://jobs.lever.co/getyourguide/abc123",
        "descriptionPlain": "Join our product team in Berlin.",
        "createdAt": 1745000000000,
    },
    {
        "text": "Product Manager",
        "categories": {"location": "New York, US", "allLocations": ["New York, US"]},
        "hostedUrl": "https://jobs.lever.co/getyourguide/xyz999",
        "descriptionPlain": "US role.",
        "createdAt": 1745000000000,
    },
]


def test_lever_filters_by_location() -> None:
    with patch("job_hunter.sources.ats.requests.get", return_value=_mock_get(LEVER_RESPONSE)):
        jobs = ats.fetch_lever_jobs("getyourguide", "GetYourGuide", "Berlin", [])
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Product Owner"


def test_lever_returns_correct_fields() -> None:
    with patch("job_hunter.sources.ats.requests.get", return_value=_mock_get(LEVER_RESPONSE)):
        jobs = ats.fetch_lever_jobs("getyourguide", "GetYourGuide", "Berlin", [])
    job = jobs[0]
    assert job["source"] == "Lever API"
    assert job["url"] == "https://jobs.lever.co/getyourguide/abc123"
    assert "Berlin" in job["snippet"]


def test_lever_no_location_filter_returns_all() -> None:
    with patch("job_hunter.sources.ats.requests.get", return_value=_mock_get(LEVER_RESPONSE)):
        jobs = ats.fetch_lever_jobs("getyourguide", "GetYourGuide", "", [])
    assert len(jobs) == 2


def test_lever_returns_empty_on_api_error() -> None:
    with patch("job_hunter.sources.ats.requests.get", side_effect=Exception("timeout")):
        jobs = ats.fetch_lever_jobs("getyourguide", "GetYourGuide", "Berlin", [])
    assert jobs == []


def test_lever_handles_dict_response_format() -> None:
    wrapped = {"postings": LEVER_RESPONSE}
    with patch("job_hunter.sources.ats.requests.get", return_value=_mock_get(wrapped)):
        jobs = ats.fetch_lever_jobs("getyourguide", "GetYourGuide", "Berlin", [])
    assert len(jobs) == 1


# ── fetch_smartrecruiters_jobs() ─────────────────────────────────────────────

SR_LISTING = {
    "content": [
        {
            "id": "abc-123",
            "name": "Product Manager",
            "location": {"city": "Berlin", "country": "DE"},
            "releasedDate": "2026-04-01",
        }
    ]
}

SR_DETAIL = {
    "jobAd": {
        "sections": [
            {"title": "Your mission", "text": "<p>Lead our product strategy.</p>"},
            {"title": "Your profile", "text": "<p>3+ years PM experience.</p>"},
        ]
    }
}


def test_smartrecruiters_fetches_description_for_matched_job() -> None:
    listing_resp = _mock_get(SR_LISTING)
    detail_resp = _mock_get(SR_DETAIL)
    with patch("job_hunter.sources.ats.requests.get", side_effect=[listing_resp, detail_resp]):
        jobs = ats.fetch_smartrecruiters_jobs("Scout24", "Scout24", "Berlin", [])
    assert len(jobs) == 1
    assert "Your mission" in jobs[0]["snippet"]
    assert "<p>" not in jobs[0]["snippet"]


def test_smartrecruiters_filters_by_location() -> None:
    listing = {
        "content": [
            {
                "id": "1",
                "name": "PM",
                "location": {"city": "Berlin", "country": "DE"},
                "releasedDate": "",
            },
            {
                "id": "2",
                "name": "PM",
                "location": {"city": "Munich", "country": "DE"},
                "releasedDate": "",
            },
        ]
    }
    detail_resp = _mock_get({"jobAd": {"sections": []}})
    with patch("job_hunter.sources.ats.requests.get", side_effect=[_mock_get(listing), detail_resp]):
        jobs = ats.fetch_smartrecruiters_jobs("Scout24", "Scout24", "Berlin", [])
    assert len(jobs) == 1
    assert "Berlin" in jobs[0]["snippet"]


def test_smartrecruiters_returns_empty_on_api_error() -> None:
    with patch("job_hunter.sources.ats.requests.get", side_effect=Exception("timeout")):
        jobs = ats.fetch_smartrecruiters_jobs("Scout24", "Scout24", "Berlin", [])
    assert jobs == []


def test_smartrecruiters_continues_if_detail_fetch_fails() -> None:
    listing_resp = _mock_get(SR_LISTING)
    with patch(
        "job_hunter.sources.ats.requests.get",
        side_effect=[listing_resp, Exception("detail timeout")],
    ):
        jobs = ats.fetch_smartrecruiters_jobs("Scout24", "Scout24", "Berlin", [])
    assert len(jobs) == 1


# ── fetch_workable_jobs() ────────────────────────────────────────────────────

WORKABLE_RESPONSE = {
    "results": [
        {
            "title": "Product Owner",
            "location": {"location": "Berlin, Germany"},
            "shortcode": "ABCDE",
            "published_on": "2026-04-01",
            "department": "Product",
        }
    ]
}


def test_workable_returns_correct_fields() -> None:
    with patch("job_hunter.sources.ats.requests.post", return_value=_mock_get(WORKABLE_RESPONSE)):
        jobs = ats.fetch_workable_jobs("mycompany", "My Company", "Berlin", [])
    assert len(jobs) == 1
    job = jobs[0]
    assert job["source"] == "Workable API"
    assert job["url"] == "https://apply.workable.com/mycompany/j/ABCDE"


def test_workable_returns_empty_on_api_error() -> None:
    with patch("job_hunter.sources.ats.requests.post", side_effect=Exception("timeout")):
        jobs = ats.fetch_workable_jobs("mycompany", "My Company", "Berlin", [])
    assert jobs == []


# ── fetch_ats_jobs() dispatcher ──────────────────────────────────────────────


def _recording_fn(calls):
    def fetch_fn(slug, company_name, location, titles, excluded=None):
        calls.append((slug, company_name, location, titles))
        return []

    return fetch_fn


def test_dispatcher_routes_greenhouse() -> None:
    company = {
        "name": "Delivery Hero",
        "career_url": "boards.greenhouse.io/deliveryhero",
        "location": "Berlin",
    }
    calls = []
    with patch.dict(ats._FETCH_FNS, {"greenhouse": _recording_fn(calls)}):
        ats.fetch_ats_jobs(company, "Berlin", ["Product Manager"])
    assert calls == [("deliveryhero", "Delivery Hero", "Berlin", ["Product Manager"])]


def test_dispatcher_routes_lever() -> None:
    company = {
        "name": "GetYourGuide",
        "career_url": "jobs.lever.co/getyourguide",
        "location": "Berlin",
    }
    calls = []
    with patch.dict(ats._FETCH_FNS, {"lever": _recording_fn(calls)}):
        ats.fetch_ats_jobs(company, "Berlin", [])
    assert calls == [("getyourguide", "GetYourGuide", "Berlin", [])]


def test_dispatcher_returns_none_for_unknown_url() -> None:
    company = {"name": "Personio", "career_url": "jobs.personio.com", "location": "Berlin"}
    result = ats.fetch_ats_jobs(company, "Berlin", [])
    assert result is None


def test_dispatcher_routes_ashby() -> None:
    company = {"name": "TestCo", "career_url": "jobs.ashbyhq.com/testco", "location": "Berlin"}
    calls = []
    with patch.dict(ats._FETCH_FNS, {"ashby": _recording_fn(calls)}):
        ats.fetch_ats_jobs(company, "Berlin", ["Product Manager"])
    assert calls == [("testco", "TestCo", "Berlin", ["Product Manager"])]


def test_dispatcher_routes_hibob() -> None:
    company = {"name": "Example HiBob Company", "career_url": "examplehibob.careers.hibob.com"}
    calls = []
    with patch.dict(ats._FETCH_FNS, {"hibob": _recording_fn(calls)}):
        ats.fetch_ats_jobs(company, "Berlin", ["Product Manager"])
    assert calls == [("examplehibob", "Example HiBob Company", "Berlin", ["Product Manager"])]


# ── fetch_ashby_jobs() ───────────────────────────────────────────────────────


# Brief listing: only id, title, locationName available from jobBoardWithTeams.
ASHBY_LIST_RESPONSE = {
    "data": {
        "board": {
            "jobPostings": [
                {"id": "uuid-1", "title": "Product Manager", "locationName": "Berlin, Germany"},
                {"id": "uuid-2", "title": "Product Manager", "locationName": "New York, USA"},
                {"id": "uuid-3", "title": "Engineering Manager", "locationName": "Berlin, Germany"},
            ]
        }
    }
}

# Per-job detail: descriptionHtml from jobPosting query.
ASHBY_DETAIL_RESPONSE = {"data": {"jobPosting": {"descriptionHtml": "<p>Great PM role in Berlin.</p>"}}}

# Alias used in field/snippet tests — detail response for first matched job.
ASHBY_RESPONSE = ASHBY_LIST_RESPONSE


def _ashby_post_side_effect(*args, **kwargs):
    """Return list response for the board query, detail response for per-job queries."""
    body = kwargs.get("json", {})
    if "board:" in (body.get("query") or ""):
        return _mock_post(ASHBY_LIST_RESPONSE)
    return _mock_post(ASHBY_DETAIL_RESPONSE)


def test_ashby_filters_by_location() -> None:
    with patch("job_hunter.sources.ats.requests.post", side_effect=_ashby_post_side_effect):
        jobs = ats.fetch_ashby_jobs("testco", "TestCo", "Berlin", [])
    assert len(jobs) == 2
    assert all("Berlin" in j["snippet"] for j in jobs)


def test_ashby_filters_by_title() -> None:
    with patch("job_hunter.sources.ats.requests.post", side_effect=_ashby_post_side_effect):
        jobs = ats.fetch_ashby_jobs("testco", "TestCo", "Berlin", ["Product Manager"])
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Product Manager"


def test_ashby_returns_correct_fields() -> None:
    with patch("job_hunter.sources.ats.requests.post", side_effect=_ashby_post_side_effect):
        jobs = ats.fetch_ashby_jobs("testco", "TestCo", "Berlin", [])
    job = jobs[0]
    assert job["source"] == "Ashby API"
    assert job["url"] == "https://jobs.ashbyhq.com/testco/uuid-1"
    assert job["company"] == "TestCo"
    assert job["posted_date_text"] == ""  # no date field in Ashby GraphQL API


def test_ashby_strips_html_from_description() -> None:
    with patch("job_hunter.sources.ats.requests.post", side_effect=_ashby_post_side_effect):
        jobs = ats.fetch_ashby_jobs("testco", "TestCo", "Berlin", [])
    assert "<p>" not in jobs[0]["snippet"]


def test_ashby_returns_empty_on_http_error() -> None:
    with patch("job_hunter.sources.ats.requests.post", return_value=_make_response(status=500, raise_error=True)):
        result = ats.fetch_ashby_jobs("testco", "TestCo", "Berlin", [])
    assert result == []


# ── fetch_hibob_jobs() ───────────────────────────────────────────────────────


def _make_playwright_mock(hrefs_and_texts: list[tuple[str, str]]):
    """Build a mock playwright context that returns the given anchor elements."""
    anchors = []
    for href, text in hrefs_and_texts:
        anchor = MagicMock()
        anchor.get_attribute.return_value = href
        anchor.text_content.return_value = text
        anchor.query_selector.return_value = None  # no location sub-element
        anchors.append(anchor)

    mock_page = MagicMock()
    mock_page.query_selector_all.return_value = anchors

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page

    mock_pw_instance = MagicMock()
    mock_pw_instance.chromium.launch.return_value = mock_browser

    mock_context = MagicMock()
    mock_context.__enter__ = MagicMock(return_value=mock_pw_instance)
    mock_context.__exit__ = MagicMock(return_value=False)

    return MagicMock(return_value=mock_context)


HIBOB_LINKS = [
    ("/jobs/a1c9baa8-22bd-48cd-9a0b-47255fb0b7ca", "Senior Product Manager"),
    ("/jobs/b2d8ccb9-33ce-59de-0b1c-58366fc1c8db", "Product Owner"),
    ("/jobs/c3e9ddc0-44df-60ef-1c2d-69477fd2d9ec", "Engineering Manager"),
]


def test_hibob_returns_matching_jobs() -> None:
    mock_sync_pw = _make_playwright_mock(HIBOB_LINKS)
    with (
        patch("job_hunter.sources.ats.sync_playwright", mock_sync_pw, create=True),
        patch.dict("sys.modules", {"playwright.sync_api": MagicMock(sync_playwright=mock_sync_pw)}),
    ):
        jobs = ats.fetch_hibob_jobs("testcorp", "TestCorp", "Berlin", ["Product Manager", "Product Owner"])
    # Both PM and PO match; Engineering Manager does not
    titles = {j["title"] for j in jobs}
    assert "Senior Product Manager" in titles
    assert "Product Owner" in titles
    assert "Engineering Manager" not in titles


def test_hibob_returns_empty_when_playwright_unavailable() -> None:
    with patch.dict("sys.modules", {"playwright.sync_api": None}):
        result = ats.fetch_hibob_jobs("testcorp", "TestCorp", "Berlin", [])
    assert result == []


def test_hibob_jobs_have_empty_snippet() -> None:
    mock_sync_pw = _make_playwright_mock(HIBOB_LINKS[:1])
    with (
        patch("job_hunter.sources.ats.sync_playwright", mock_sync_pw, create=True),
        patch.dict("sys.modules", {"playwright.sync_api": MagicMock(sync_playwright=mock_sync_pw)}),
    ):
        jobs = ats.fetch_hibob_jobs("testcorp", "TestCorp", "Berlin", [])
    # Snippets are intentionally empty — enriched later by orchestrator
    assert all(j["snippet"] == "" for j in jobs)


def test_hibob_source_label() -> None:
    mock_sync_pw = _make_playwright_mock(HIBOB_LINKS[:1])
    with (
        patch("job_hunter.sources.ats.sync_playwright", mock_sync_pw, create=True),
        patch.dict("sys.modules", {"playwright.sync_api": MagicMock(sync_playwright=mock_sync_pw)}),
    ):
        jobs = ats.fetch_hibob_jobs("testcorp", "TestCorp", "Berlin", [])
    assert all(j["source"] == "HiBob" for j in jobs)
