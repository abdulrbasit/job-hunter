"""Tests for new job source modules — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

from conftest import mk_params

from job_hunter.models import JobPosting
from job_hunter.sources.boards.adzuna import AdzunaSource
from job_hunter.sources.boards.bayt import BaytSource
from job_hunter.sources.boards.careerjet import CareerjetSource
from job_hunter.sources.boards.gulftalent import GulfTalentSource
from job_hunter.sources.boards.jobbank import JobBankSource
from job_hunter.sources.boards.jobicy import JobicySource
from job_hunter.sources.boards.jobstreet import JobStreetSource
from job_hunter.sources.boards.mycareersfuture import MyCareersFutureSource
from job_hunter.sources.boards.reed import ReedSource
from job_hunter.sources.boards.remoteok import RemoteOKSource
from job_hunter.sources.boards.weworkremotely import WeWorkRemotelySource
from job_hunter.sources.boards.workingnomads import WorkingNomadsSource

# ── helpers ──────────────────────────────────────────────────────────────────


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


def _mock_get_bytes(content: bytes, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.content = content
    return resp


_REGIONS = {"EU": {"location": "Europe", "country": "DE"}}
_GB_REGIONS = {"GB": {"location": "London", "country": "GB"}}
_EXCL = {"exclusions": {"title_terms": []}}


# ═══════════════════════════════════════════════════════════════════════════
# Jobicy
# ═══════════════════════════════════════════════════════════════════════════

_JOBICY_CFG = {"http": {"job_boards": {"jobicy": {"enabled": True, "timeout_seconds": 10}}}}

_JOBICY_JOB = {
    "jobTitle": "Software Engineer",
    "companyName": "ACME",
    "url": "https://example.com/1",
    "pubDate": "2026-06-01T00:00:00Z",
    "jobGeo": "Remote",
    "jobDescription": "<p>An engineering role.</p>",
}


class TestJobicySource:
    def test_name(self) -> None:
        assert JobicySource().source_name == "jobicy"

    def test_is_enabled_respects_config(self) -> None:
        disabled = {"http": {"job_boards": {"jobicy": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.jobicy.get_api_config", return_value=disabled):
            assert JobicySource().is_enabled(disabled) is False

    def test_fetch_returns_job_postings(self) -> None:
        get_mock = MagicMock(return_value=_make_response(json_data={"jobs": [_JOBICY_JOB]}))
        with (
            patch(
                "job_hunter.sources.boards.jobicy.get_api_config",
                return_value=_JOBICY_CFG,
            ),
            patch("job_hunter.sources.boards.jobicy.reserve_api_call", return_value=True),
            patch("job_hunter.sources.boards.jobicy.requests.get", get_mock),
            patch("job_hunter.sources.boards.jobicy._read_cache", return_value=None),
            patch("job_hunter.sources.boards.jobicy._write_cache"),
        ):
            jobs = JobicySource().fetch(mk_params(["Software Engineer"], _REGIONS))
        assert len(jobs) == 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].title == "Software Engineer"
        assert jobs[0].source == "Jobicy"
        assert get_mock.call_args.kwargs["params"]["geo"] == "germany"

    def test_fetch_skips_unsupported_geo(self) -> None:
        get_mock = MagicMock(return_value=_make_response(json_data={"jobs": [_JOBICY_JOB]}))
        with (
            patch(
                "job_hunter.sources.boards.jobicy.get_api_config",
                return_value=_JOBICY_CFG,
            ),
            patch("job_hunter.sources.boards.jobicy.reserve_api_call", return_value=True),
            patch("job_hunter.sources.boards.jobicy.requests.get", get_mock),
        ):
            jobs = JobicySource().fetch(
                mk_params(["Software Engineer"], {"sd": {"country": "SD", "location": "Khartoum"}})
            )
        assert jobs == []
        get_mock.assert_not_called()

    def test_fetch_returns_empty_when_disabled(self) -> None:
        disabled = {"http": {"job_boards": {"jobicy": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.jobicy.get_api_config", return_value=disabled):
            jobs = JobicySource().fetch(mk_params(["Software Engineer"], _REGIONS))
        assert jobs == []


# ═══════════════════════════════════════════════════════════════════════════
# RemoteOK
# ═══════════════════════════════════════════════════════════════════════════

_REMOTEOK_CFG = {"http": {"job_boards": {"remoteok": {"enabled": True, "timeout_seconds": 10}}}}

_REMOTEOK_METADATA = {"legal": "see remoteok.com"}

_REMOTEOK_JOB = {
    "position": "Software Engineer",
    "company": "RemoteCo",
    "url": "https://remoteok.com/1",
    "date": "2026-06-01T00:00:00Z",
    "location": "Worldwide",
    "tags": ["python", "django"],
    "description": "",
}


class TestRemoteOKSource:
    def test_name(self) -> None:
        assert RemoteOKSource().source_name == "remoteok"

    def test_is_enabled_respects_config(self) -> None:
        disabled = {"http": {"job_boards": {"remoteok": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.remoteok.get_api_config", return_value=disabled):
            assert RemoteOKSource().is_enabled(disabled) is False

    def test_fetch_returns_job_postings(self) -> None:
        feed = [_REMOTEOK_METADATA, _REMOTEOK_JOB]
        with (
            patch(
                "job_hunter.sources.boards.remoteok.get_api_config",
                return_value=_REMOTEOK_CFG,
            ),
            patch(
                "job_hunter.sources.boards.remoteok.requests.get",
                return_value=_make_response(json_data=feed),
            ),
        ):
            jobs = RemoteOKSource().fetch(mk_params(["Software Engineer"], _REGIONS))
        assert len(jobs) == 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].title == "Software Engineer"
        assert jobs[0].source == "RemoteOK"

    def test_fetch_returns_empty_when_disabled(self) -> None:
        disabled = {"http": {"job_boards": {"remoteok": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.remoteok.get_api_config", return_value=disabled):
            jobs = RemoteOKSource().fetch(mk_params(["Software Engineer"], _REGIONS))
        assert jobs == []

    def test_fetch_does_not_early_filter_jobs_outside_region_location(self) -> None:
        """RemoteOK no longer drops a job locally just because its location string
        doesn't match the region — that decision moves to JobPolicy/quality_gate.
        location_restrictions is still populated so the downstream check has a signal."""
        onsite_job = {**_REMOTEOK_JOB, "location": "San Francisco, CA"}
        feed = [_REMOTEOK_METADATA, onsite_job]
        with (
            patch(
                "job_hunter.sources.boards.remoteok.get_api_config",
                return_value=_REMOTEOK_CFG,
            ),
            patch(
                "job_hunter.sources.boards.remoteok.requests.get",
                return_value=_make_response(json_data=feed),
            ),
        ):
            jobs = RemoteOKSource().fetch(mk_params(["Software Engineer"], _REGIONS))
        assert len(jobs) == 1
        assert jobs[0].location == "San Francisco, CA"
        assert jobs[0].location_restrictions == ["San Francisco, CA"]

    def test_fetch_keeps_worldwide_and_remote_jobs(self) -> None:
        for broad_location in ("Worldwide", "Remote", "Anywhere"):
            job = {**_REMOTEOK_JOB, "location": broad_location}
            feed = [_REMOTEOK_METADATA, job]
            with (
                patch(
                    "job_hunter.sources.boards.remoteok.get_api_config",
                    return_value=_REMOTEOK_CFG,
                ),
                patch(
                    "job_hunter.sources.boards.remoteok.requests.get",
                    return_value=_make_response(json_data=feed),
                ),
            ):
                jobs = RemoteOKSource().fetch(mk_params(["Software Engineer"], _REGIONS))
            assert len(jobs) == 1, f"{broad_location!r} should not be dropped"


# ═══════════════════════════════════════════════════════════════════════════
# WeWorkRemotely
# ═══════════════════════════════════════════════════════════════════════════

_WWR_CFG = {"http": {"job_boards": {"weworkremotely": {"enabled": True, "timeout_seconds": 10}}}}

_WWR_RSS_MATCHING = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>We Work Remotely</title>
    <item>
      <title>ACME Corp: Software Engineer</title>
      <link>https://weworkremotely.com/job/1</link>
      <pubDate>Mon, 01 Jun 2026 12:00:00 +0000</pubDate>
      <description>Build great things from Europe.</description>
    </item>
    <item>
      <title>OtherCo: Marketing Manager</title>
      <link>https://weworkremotely.com/job/2</link>
      <pubDate>Mon, 01 Jun 2026 12:00:00 +0000</pubDate>
      <description>Market things.</description>
    </item>
  </channel>
</rss>"""

_WWR_RSS_WITH_REGION = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>We Work Remotely</title>
    <item>
      <title>ACME Corp: Software Engineer</title>
      <link>https://weworkremotely.com/job/3</link>
      <pubDate>Mon, 01 Jun 2026 12:00:00 +0000</pubDate>
      <region>Anywhere in the World</region>
      <country>United States</country>
      <description>Build great things.</description>
    </item>
  </channel>
</rss>"""


# ═══════════════════════════════════════════════════════════════════════════
# Adzuna — pagination
# ═══════════════════════════════════════════════════════════════════════════

_ADZUNA_CFG_PAGINATE = {"http": {"job_boards": {"adzuna": {"enabled": True, "results_per_page": 2}}}}

_ADZUNA_JOB = lambda n: {  # noqa: E731
    "title": "Software Engineer",
    "company": {"display_name": f"Co{n}"},
    "redirect_url": f"https://adzuna.com/{n}",
    "created": "2026-06-01T00:00:00Z",
    "location": {"display_name": "Berlin"},
    "description": "A role.",
}

_ADZUNA_GB_REGIONS = {"GB": {"location": "", "country": "GB"}}

_REED_CFG_PAGINATE = {"http": {"job_boards": {"reed": {"enabled": True, "results_wanted": 2}}}}

_REED_JOB = lambda n: {  # noqa: E731
    "jobTitle": "Software Engineer",
    "employerName": f"Co{n}",
    "jobUrl": f"https://reed.co.uk/{n}",
    "date": "01/06/2026",
    "locationName": "London",
    "jobDescription": "A role.",
}


# ═══════════════════════════════════════════════════════════════════════════
# Regional sources — MyCareersFuture / JobBank / GulfTalent / JobStreet
# ═══════════════════════════════════════════════════════════════════════════


_EMPTY_CFG = {"http": {"job_boards": {}}}
_CONFIG = {"exclusions": {"title_terms": []}}


def _disabled(board: str) -> dict:
    return {"http": {"job_boards": {board: {"enabled": False}}}}


# ── Region fixtures ──────────────────────────────────────────────────────────
_SG = {"sg": {"country": "SG", "location": "Singapore"}}
_NL = {"nl": {"country": "NL", "location": "Amsterdam"}}
_CA = {"ca": {"country": "CA", "location": "Toronto"}}
_FR = {"fr": {"country": "FR", "location": "Paris"}}
_ID = {"id": {"country": "ID", "location": "Jakarta"}}
_IE = {"ie": {"country": "IE", "location": "Dublin"}}
_AE = {"ae": {"country": "AE", "location": "Dubai"}}
_SA = {"sa": {"country": "SA", "location": "Riyadh"}}
_MY = {"my": {"country": "MY", "location": "Kuala Lumpur"}}
_DE = {"de": {"country": "DE", "location": "Berlin"}}
_GB = {"gb": {"country": "GB", "location": "London"}}

# ── Data fixtures used by class tests ────────────────────────────────────────

_MCF_RESPONSE = {
    "results": [
        {
            "uuid": "abc-123",
            "title": "Product Manager",
            "postedCompany": {"name": "GovTech"},
            "description": "<p>Lead product strategy.</p>",
            "metadata": {"dates": {"posting": "2026-06-01T00:00:00"}},
            "salary": {"minimum": 6000, "maximum": 9000},
            "address": {"street": "One North"},
        }
    ]
}

_JB_HTML = """<html><body>
<article class="resultcount">
  <h3><a href="/job-posting/12345">Product Manager</a></h3>
  <span class="business-title">CanadaCorp</span>
  <span class="location">Toronto, ON</span>
  <span class="date">2026-06-01</span>
</article></body></html>"""

# GulfTalent's fetch loop treats responses <=200 chars as blocked/empty (real anti-bot
# block pages are tiny) — short synthetic fixtures need this padding to read as real HTML.
_PAD_200 = "<!-- " + "x" * 200 + " -->"

_GT_HTML = """<html><body>
<div class="job-listing">
  <h2><a class="job-title" href="/jobs/456">Product Manager</a></h2>
  <span class="company-name">GulfCorp</span>
  <span class="location">Dubai, UAE</span>
</div></body></html>"""

_GT_HTML_INTERN = """<html><body>
<div class="job-listing">
  <h2><a class="job-title" href="/jobs/456">Product Manager</a></h2>
  <span class="company-name">GulfCorp</span>
  <span class="location">Dubai, UAE</span>
</div>
<div class="job-listing">
  <h2><a class="job-title" href="/jobs/457">Product Manager Intern</a></h2>
  <span class="company-name">GulfCorp</span>
  <span class="location">Dubai, UAE</span>
</div></body></html>"""

_BAYT_HTML = """<html><body>
<ul>
<li data-js-job class="has-pointer-d" data-job-id="1">
  <h2><a data-js-link href="/en/uae/jobs/product-manager-1/" title="Product Manager">Product Manager</a></h2>
  <div class="job-company-location-wrapper">
    <div><a class="t-default t-bold" href="/en/company/gulfcorp/">GulfCorp</a></div>
    <div class="t-mute"><a><span>Dubai</span></a>, <a><span>UAE</span></a></div>
  </div>
  <div class="jb-descr">Summary: Lead product strategy.</div>
  <div class="jb-date">1 hour ago</div>
</li>
</ul></body></html>"""

_BAYT_HTML_INTERN = """<html><body>
<ul>
<li data-js-job class="has-pointer-d" data-job-id="1">
  <h2><a data-js-link href="/en/uae/jobs/product-manager-1/" title="Product Manager">Product Manager</a></h2>
  <div class="job-company-location-wrapper">
    <div><a class="t-default t-bold" href="/en/company/gulfcorp/">GulfCorp</a></div>
    <div class="t-mute"><a><span>Dubai</span></a>, <a><span>UAE</span></a></div>
  </div>
</li>
<li data-js-job class="has-pointer-d" data-job-id="2">
  <h2><a data-js-link href="/en/uae/jobs/product-manager-intern-2/" title="Product Manager Intern">Product Manager Intern</a></h2>
  <div class="job-company-location-wrapper">
    <div><a class="t-default t-bold" href="/en/company/gulfcorp/">GulfCorp</a></div>
    <div class="t-mute"><a><span>Dubai</span></a>, <a><span>UAE</span></a></div>
  </div>
</li>
</ul></body></html>"""

_BAYT_HTML_PAGE1_WITH_NEXT = """<html><head>
<link rel="next" href="https://www.bayt.com/en/uae/jobs/product-manager-jobs/?page=2">
</head><body>
<ul>
<li data-js-job class="has-pointer-d" data-job-id="1">
  <h2><a data-js-link href="/en/uae/jobs/product-manager-1/" title="Product Manager">Product Manager</a></h2>
  <div class="job-company-location-wrapper">
    <div><a class="t-default t-bold" href="/en/company/gulfcorp/">GulfCorp</a></div>
    <div class="t-mute"><a><span>Dubai</span></a>, <a><span>UAE</span></a></div>
  </div>
</li>
</ul></body></html>"""

_BAYT_HTML_PAGE2 = """<html><body>
<ul>
<li data-js-job class="has-pointer-d" data-job-id="3">
  <h2><a data-js-link href="/en/uae/jobs/senior-product-manager-3/" title="Senior Product Manager">Senior Product Manager</a></h2>
  <div class="job-company-location-wrapper">
    <div><a class="t-default t-bold" href="/en/company/gulfcorp/">GulfCorp</a></div>
    <div class="t-mute"><a><span>Dubai</span></a>, <a><span>UAE</span></a></div>
  </div>
</li>
</ul></body></html>"""

_JS_RESPONSE = {
    "data": {
        "jobs": [
            {
                "id": "js-9001",
                "title": "Product Manager",
                "advertiser": {"description": "JobStreetCo"},
                "teaser": "Drive product growth across SEA.",
                "salary": {"min": 5000, "max": 8000},
                "listingDate": "2026-06-01",
            }
        ]
    }
}


# ═══════════════════════════════════════════════════════════════════════════
# Class-level JobSourceAdapter tests
# ═══════════════════════════════════════════════════════════════════════════


class TestGulfTalentSource:
    def test_name(self) -> None:
        assert GulfTalentSource().source_name == "gulftalent"

    def test_is_enabled_false_when_disabled(self) -> None:
        disabled = {"http": {"job_boards": {"gulftalent": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.gulftalent.get_api_config", return_value=disabled):
            assert GulfTalentSource().is_enabled(disabled) is False

    def test_fetch_returns_job_postings(self) -> None:
        with (
            patch(
                "job_hunter.sources.boards.gulftalent.get_api_config",
                return_value=_EMPTY_CFG,
            ),
            patch(
                "job_hunter.sources.boards.gulftalent.requests.get",
                return_value=_make_response(text=_GT_HTML),
            ),
        ):
            jobs = GulfTalentSource().fetch(mk_params(["Product Manager"], _AE))
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "GulfTalent"

    def test_fetch_respects_excluded_title_terms_regardless_of_word_order(self) -> None:
        """Regression: GulfTalent used to call _parse_cards(..., [], ...), silently
        dropping params.excluded_title_terms so "Product Manager Intern" leaked through."""
        with (
            patch(
                "job_hunter.sources.boards.gulftalent.get_api_config",
                return_value=_EMPTY_CFG,
            ),
            patch(
                "job_hunter.sources.boards.gulftalent.requests.get",
                return_value=_make_response(text=_GT_HTML_INTERN),
            ),
        ):
            jobs = GulfTalentSource().fetch(mk_params(["Product Manager"], _AE, excluded_title_terms=["intern"]))
        titles = [job.title for job in jobs]
        assert "Product Manager" in titles
        assert "Product Manager Intern" not in titles

    def test_fetch_follows_next_page_link(self) -> None:
        page1 = """<html><head>
        <link rel="next" href="https://www.gulftalent.com/jobs?keyword=product+manager&page=2">
        </head><body>
        <div class="job-listing">
          <h2><a class="job-title" href="/jobs/1">Product Manager</a></h2>
          <span class="company-name">GulfCorp</span>
        </div></body></html>"""
        page2 = """<html><body>
        <div class="job-listing">
          <h2><a class="job-title" href="/jobs/2">Senior Product Manager</a></h2>
          <span class="company-name">GulfCorp</span>
        </div></body></html>"""
        with (
            patch(
                "job_hunter.sources.boards.gulftalent.get_api_config",
                return_value=_EMPTY_CFG,
            ),
            patch(
                "job_hunter.sources.boards.gulftalent.requests.get",
                side_effect=[_make_response(text=page1), _make_response(text=page2)],
            ) as get_mock,
        ):
            jobs = GulfTalentSource().fetch(mk_params(["Product Manager"], _AE))
        assert {j.title for j in jobs} == {"Product Manager", "Senior Product Manager"}
        assert get_mock.call_count == 2
        assert get_mock.call_args_list[1].args[0] == "https://www.gulftalent.com/jobs?keyword=product+manager&page=2"

    def test_fetch_stops_when_no_next_link(self) -> None:
        with (
            patch(
                "job_hunter.sources.boards.gulftalent.get_api_config",
                return_value=_EMPTY_CFG,
            ),
            patch(
                "job_hunter.sources.boards.gulftalent.requests.get",
                return_value=_make_response(text=_GT_HTML),
            ) as get_mock,
        ):
            GulfTalentSource().fetch(mk_params(["Product Manager"], _AE))
        assert get_mock.call_count == 1

    def test_fetch_returns_empty_for_no_results_page(self) -> None:
        no_results_html = (
            _PAD_200
            + """<html><body>
        <div class="no-results">No jobs found matching your search.</div>
        </body></html>"""
        )
        with (
            patch(
                "job_hunter.sources.boards.gulftalent.get_api_config",
                return_value=_EMPTY_CFG,
            ),
            patch(
                "job_hunter.sources.boards.gulftalent.requests.get",
                return_value=_make_response(text=no_results_html),
            ),
        ):
            jobs = GulfTalentSource().fetch(mk_params(["Product Manager"], _AE))
        assert jobs == []

    def test_fetch_returns_empty_for_blocked_or_empty_response(self) -> None:
        with (
            patch(
                "job_hunter.sources.boards.gulftalent.get_api_config",
                return_value=_EMPTY_CFG,
            ),
            patch(
                "job_hunter.sources.boards.gulftalent.requests.get",
                return_value=_make_response(text="", status_code=403),
            ),
        ):
            jobs = GulfTalentSource().fetch(mk_params(["Product Manager"], _AE))
        assert jobs == []

    def test_fetch_extracts_jsonld_jobposting_when_no_cards(self) -> None:
        jsonld_html = """<html><head>
        <script type="application/ld+json">
        {"@type": "JobPosting", "title": "Product Manager", "hiringOrganization": {"name": "GulfCorp"},
         "applyUrl": "https://www.gulftalent.com/jobs/789", "jobLocation": {"address": {"addressCountry": "AE"}}}
        </script>
        </head><body></body></html>"""
        with (
            patch(
                "job_hunter.sources.boards.gulftalent.get_api_config",
                return_value=_EMPTY_CFG,
            ),
            patch(
                "job_hunter.sources.boards.gulftalent.requests.get",
                return_value=_make_response(text=jsonld_html),
            ),
        ):
            jobs = GulfTalentSource().fetch(mk_params(["Product Manager"], _AE))
        assert len(jobs) == 1
        assert jobs[0].title == "Product Manager"
        assert jobs[0].url == "https://www.gulftalent.com/jobs/789"

    def test_fetch_extracts_embedded_script_data_when_no_cards_or_jsonld(self) -> None:
        embedded_html = (
            _PAD_200
            + """<html><body>
        <script>window.__INITIAL_STATE__ = {"jobs": [
            {"title": "Product Manager", "url": "/jobs/321", "company": "GulfCorp"}
        ]};</script>
        </body></html>"""
        )
        with (
            patch(
                "job_hunter.sources.boards.gulftalent.get_api_config",
                return_value=_EMPTY_CFG,
            ),
            patch(
                "job_hunter.sources.boards.gulftalent.requests.get",
                return_value=_make_response(text=embedded_html),
            ),
        ):
            jobs = GulfTalentSource().fetch(mk_params(["Product Manager"], _AE))
        assert len(jobs) == 1
        assert jobs[0].title == "Product Manager"
        assert jobs[0].url == "https://www.gulftalent.com/jobs/321"

    def test_fetch_uses_anchor_fallback_when_no_cards(self) -> None:
        anchor_html = (
            _PAD_200
            + """<html><body>
        <a href="/jobs/999-product-manager">Product Manager</a>
        </body></html>"""
        )
        with (
            patch(
                "job_hunter.sources.boards.gulftalent.get_api_config",
                return_value=_EMPTY_CFG,
            ),
            patch(
                "job_hunter.sources.boards.gulftalent.requests.get",
                return_value=_make_response(text=anchor_html),
            ),
        ):
            jobs = GulfTalentSource().fetch(mk_params(["Product Manager"], _AE))
        assert len(jobs) == 1
        assert jobs[0].title == "Product Manager"


class TestBaytSource:
    def test_name(self) -> None:
        assert BaytSource().source_name == "bayt"

    def test_is_enabled_false_when_disabled(self) -> None:
        disabled = {"http": {"job_boards": {"bayt": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.bayt.get_api_config", return_value=disabled):
            assert BaytSource().is_enabled(disabled) is False

    def test_fetch_skips_unsupported_country(self) -> None:
        with patch("job_hunter.sources.boards.bayt.get_api_config", return_value=_EMPTY_CFG):
            jobs = BaytSource().fetch(mk_params(["Product Manager"], _DE))
        assert jobs == []

    def test_fetch_returns_job_postings(self) -> None:
        with (
            patch("job_hunter.sources.boards.bayt.get_api_config", return_value=_EMPTY_CFG),
            patch(
                "job_hunter.sources.boards.bayt.requests.get",
                return_value=_make_response(text=_BAYT_HTML),
            ),
        ):
            jobs = BaytSource().fetch(mk_params(["Product Manager"], _AE))
        assert len(jobs) == 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "Bayt"
        assert jobs[0].title == "Product Manager"
        assert jobs[0].company == "GulfCorp"
        assert jobs[0].location == "Dubai, UAE"

    def test_fetch_respects_excluded_title_terms(self) -> None:
        with (
            patch("job_hunter.sources.boards.bayt.get_api_config", return_value=_EMPTY_CFG),
            patch(
                "job_hunter.sources.boards.bayt.requests.get",
                return_value=_make_response(text=_BAYT_HTML_INTERN),
            ),
        ):
            jobs = BaytSource().fetch(mk_params(["Product Manager"], _AE, excluded_title_terms=["intern"]))
        titles = [j.title for j in jobs]
        assert "Product Manager" in titles
        assert "Product Manager Intern" not in titles

    def test_fetch_follows_next_page_link(self) -> None:
        with (
            patch("job_hunter.sources.boards.bayt.get_api_config", return_value=_EMPTY_CFG),
            patch(
                "job_hunter.sources.boards.bayt.requests.get",
                side_effect=[_make_response(text=_BAYT_HTML_PAGE1_WITH_NEXT), _make_response(text=_BAYT_HTML_PAGE2)],
            ) as get_mock,
        ):
            jobs = BaytSource().fetch(mk_params(["Product Manager"], _AE))
        assert {j.title for j in jobs} == {"Product Manager", "Senior Product Manager"}
        assert get_mock.call_count == 2


class TestJobBankSource:
    def test_name(self) -> None:
        assert JobBankSource().source_name == "jobbank"

    def test_is_enabled_false_when_disabled(self) -> None:
        disabled = {"http": {"job_boards": {"jobbank": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.jobbank.get_api_config", return_value=disabled):
            assert JobBankSource().is_enabled(disabled) is False

    def test_fetch_returns_job_postings(self) -> None:
        with (
            patch("job_hunter.sources.boards.jobbank.get_api_config", return_value=_EMPTY_CFG),
            patch(
                "job_hunter.sources.boards.jobbank.requests.get",
                return_value=_make_response(text=_JB_HTML),
            ),
        ):
            jobs = JobBankSource().fetch(mk_params(["Product Manager"], _CA))
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "JobBank Canada"


class TestJobStreetSource:
    def test_name(self) -> None:
        assert JobStreetSource().source_name == "jobstreet"

    def test_is_enabled_false_when_disabled(self) -> None:
        disabled = {"http": {"job_boards": {"jobstreet": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.jobstreet.get_api_config", return_value=disabled):
            assert JobStreetSource().is_enabled(disabled) is False

    def test_fetch_returns_job_postings(self) -> None:
        with (
            patch(
                "job_hunter.sources.boards.jobstreet.get_api_config",
                return_value=_EMPTY_CFG,
            ),
            patch(
                "job_hunter.sources.boards.jobstreet.requests.get",
                return_value=_make_response(json_data=_JS_RESPONSE),
            ),
        ):
            jobs = JobStreetSource().fetch(mk_params(["Product Manager"], _MY))
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "JobStreet"

    def test_deep_max_results_fetches_more_pages_than_standard(self) -> None:
        # A full page (>= _PAGE_SIZE=30) so the adapter never breaks early on a short page.
        full_page = {
            "data": {
                "jobs": [
                    {"id": f"js-{i}", "title": "Product Manager", "advertiser": {"description": "Co"}}
                    for i in range(30)
                ]
            }
        }
        with (
            patch("job_hunter.sources.boards.jobstreet.get_api_config", return_value=_EMPTY_CFG),
            patch(
                "job_hunter.sources.boards.jobstreet.requests.get",
                return_value=_make_response(json_data=full_page),
            ) as get_mock,
        ):
            JobStreetSource().fetch(mk_params(["Product Manager"], _MY, max_results=50))
            standard_calls = get_mock.call_count

        with (
            patch("job_hunter.sources.boards.jobstreet.get_api_config", return_value=_EMPTY_CFG),
            patch(
                "job_hunter.sources.boards.jobstreet.requests.get",
                return_value=_make_response(json_data=full_page),
            ) as get_mock,
        ):
            JobStreetSource().fetch(mk_params(["Product Manager"], _MY, max_results=150))
            deep_calls = get_mock.call_count

        assert standard_calls == 3  # DEFAULT_PAGED_SOURCE_CAP, unchanged from before this change
        assert deep_calls > standard_calls


class TestMyCareersFutureSource:
    def test_name(self) -> None:
        assert MyCareersFutureSource().source_name == "mycareersfuture"

    def test_is_enabled_false_when_disabled(self) -> None:
        disabled = {"http": {"job_boards": {"mycareersfuture": {"enabled": False}}}}
        with patch(
            "job_hunter.sources.boards.mycareersfuture.get_api_config",
            return_value=disabled,
        ):
            assert MyCareersFutureSource().is_enabled(disabled) is False

    def test_fetch_returns_job_postings(self) -> None:
        with (
            patch(
                "job_hunter.sources.boards.mycareersfuture.get_api_config",
                return_value=_EMPTY_CFG,
            ),
            patch(
                "job_hunter.sources.boards.mycareersfuture.requests.get",
                return_value=_make_response(json_data=_MCF_RESPONSE),
            ),
        ):
            jobs = MyCareersFutureSource().fetch(mk_params(["Product Manager"], _SG))
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "MyCareersFuture"


class TestWeWorkRemotelySource:
    def test_name(self) -> None:
        assert WeWorkRemotelySource().source_name == "weworkremotely"

    def test_is_enabled_false_when_disabled(self) -> None:
        disabled = {"http": {"job_boards": {"weworkremotely": {"enabled": False}}}}
        with patch("job_hunter.sources.source_config.get_api_config", return_value=disabled):
            assert WeWorkRemotelySource().is_enabled(disabled) is False

    def test_fetch_returns_job_postings(self) -> None:
        with (
            patch(
                "job_hunter.sources.source_config.get_api_config",
                return_value=_WWR_CFG,
            ),
            patch(
                "job_hunter.sources.boards.weworkremotely.requests.get",
                return_value=_mock_get_bytes(_WWR_RSS_MATCHING),
            ),
        ):
            jobs = WeWorkRemotelySource().fetch(mk_params(["Software Engineer"], _REGIONS))
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "WeWorkRemotely"

    def test_fetch_uses_structured_region_and_country_fields(self) -> None:
        """The RSS feed carries real <region>/<country> tags — use those instead of
        guessing location_restrictions from description text."""
        with (
            patch(
                "job_hunter.sources.source_config.get_api_config",
                return_value=_WWR_CFG,
            ),
            patch(
                "job_hunter.sources.boards.weworkremotely.requests.get",
                return_value=_mock_get_bytes(_WWR_RSS_WITH_REGION),
            ),
        ):
            jobs = WeWorkRemotelySource().fetch(mk_params(["Software Engineer"], _REGIONS))
        assert len(jobs) == 1
        assert jobs[0].location == "United States"
        assert jobs[0].location_restrictions == ["Anywhere in the World", "United States"]


class TestReedSource:
    def test_name(self) -> None:
        src = ReedSource.__new__(ReedSource)
        src._api_key = "test-key"
        assert src.source_name == "reed"

    def test_is_enabled_false_when_disabled(self) -> None:
        src = ReedSource.__new__(ReedSource)
        src._api_key = "test-key"
        disabled = {"http": {"job_boards": {"reed": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.reed.get_api_config", return_value=disabled):
            assert src.is_enabled(disabled) is False

    def test_fetch_returns_job_postings(self) -> None:
        src = ReedSource.__new__(ReedSource)
        src._api_key = "test-key"
        config = {"http": {"job_boards": {"reed": {"enabled": True, "results_wanted": 1}}}}
        page_data = {"results": [_REED_JOB(1)]}
        with (
            patch("job_hunter.sources.boards.reed.get_api_config", return_value=config),
            patch("job_hunter.sources.boards.reed.reserve_api_call", return_value=True),
            patch(
                "job_hunter.sources.boards.reed.requests.get",
                return_value=_make_response(json_data=page_data),
            ),
        ):
            jobs = src.fetch(mk_params(["Software Engineer"], _GB_REGIONS))
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "Reed"


class TestAdzunaSource:
    def test_name(self) -> None:
        src = AdzunaSource.__new__(AdzunaSource)
        src._app_id = "app123"
        src._api_key = "key123"
        assert src.source_name == "adzuna"

    def test_is_enabled_false_when_disabled(self) -> None:
        src = AdzunaSource.__new__(AdzunaSource)
        src._app_id = "app123"
        src._api_key = "key123"
        disabled = {"http": {"job_boards": {"adzuna": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.adzuna.get_api_config", return_value=disabled):
            assert src.is_enabled(disabled) is False

    def test_fetch_returns_job_postings(self) -> None:
        src = AdzunaSource.__new__(AdzunaSource)
        src._app_id = "app123"
        src._api_key = "key123"
        config = {"http": {"job_boards": {"adzuna": {"enabled": True, "results_per_page": 1}}}}
        page_data = {"results": [_ADZUNA_JOB(1)]}
        with (
            patch("job_hunter.sources.boards.adzuna.get_api_config", return_value=config),
            patch("job_hunter.sources.boards.adzuna.reserve_api_call", return_value=True),
            patch(
                "job_hunter.sources.boards.adzuna.requests.get",
                return_value=_make_response(json_data=page_data),
            ),
        ):
            jobs = src.fetch(mk_params(["Software Engineer"], _ADZUNA_GB_REGIONS))
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "Adzuna"

    def test_deep_max_results_fetches_more_pages_than_standard(self) -> None:
        """Regression: paged adapters used to ignore params.max_results entirely
        (always source_page_cap()); deep/backfill attempts must fetch more pages."""
        src = AdzunaSource.__new__(AdzunaSource)
        src._app_id = "app123"
        src._api_key = "key123"
        config = {"http": {"job_boards": {"adzuna": {"enabled": True, "results_per_page": 1}}}}
        page_data = {"results": [_ADZUNA_JOB(1)]}  # never < results_per_page, so pages never break early

        with (
            patch("job_hunter.sources.boards.adzuna.get_api_config", return_value=config),
            patch("job_hunter.sources.boards.adzuna.reserve_api_call", return_value=True),
            patch(
                "job_hunter.sources.boards.adzuna.requests.get",
                return_value=_make_response(json_data=page_data),
            ) as get_mock,
        ):
            src.fetch(mk_params(["Software Engineer"], _ADZUNA_GB_REGIONS, max_results=50))
            standard_calls = get_mock.call_count

        with (
            patch("job_hunter.sources.boards.adzuna.get_api_config", return_value=config),
            patch("job_hunter.sources.boards.adzuna.reserve_api_call", return_value=True),
            patch(
                "job_hunter.sources.boards.adzuna.requests.get",
                return_value=_make_response(json_data=page_data),
            ) as get_mock,
        ):
            src.fetch(mk_params(["Software Engineer"], _ADZUNA_GB_REGIONS, max_results=150))
            deep_calls = get_mock.call_count

        assert standard_calls == 1
        assert deep_calls > standard_calls


# ═══════════════════════════════════════════════════════════════════════════
# Careerjet
# ═══════════════════════════════════════════════════════════════════════════

_CAREERJET_CFG = {"http": {"job_boards": {"careerjet": {"enabled": True, "affid": "test123", "timeout_seconds": 10}}}}

_CAREERJET_JOB = {
    "title": "Software Engineer",
    "company": "TechCorp",
    "url": "https://careerjet.com/job/1",
    "date": "2026-06-01",
    "locations": "Berlin, Germany",
    "description": "Build great systems.",
}


class TestCareerjetSource:
    def test_name(self) -> None:
        assert CareerjetSource().source_name == "careerjet"

    def test_is_enabled_false_when_no_affid(self) -> None:
        config = {"http": {"job_boards": {"careerjet": {"enabled": True, "affid": ""}}}}
        with patch("job_hunter.sources.boards.careerjet.get_api_config", return_value=config):
            assert CareerjetSource().is_enabled(config) is False

    def test_is_enabled_false_when_disabled(self) -> None:
        config = {"http": {"job_boards": {"careerjet": {"enabled": False, "affid": "x"}}}}
        with patch("job_hunter.sources.boards.careerjet.get_api_config", return_value=config):
            assert CareerjetSource().is_enabled(config) is False

    def test_fetch_returns_job_postings(self) -> None:
        response = {"jobs": [_CAREERJET_JOB], "total": 1}
        get_mock = MagicMock(return_value=_make_response(json_data=response))
        with (
            patch(
                "job_hunter.sources.boards.careerjet.get_api_config",
                return_value=_CAREERJET_CFG,
            ),
            patch("job_hunter.sources.boards.careerjet.requests.get", get_mock),
        ):
            jobs = CareerjetSource().fetch(mk_params(["Software Engineer"], _DE))
        assert len(jobs) == 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "Careerjet"
        assert jobs[0].title == "Software Engineer"
        params = get_mock.call_args.kwargs["params"]
        assert params["affid"] == "test123"
        assert params["locale_code"] == "de_DE"

    def test_fetch_uses_correct_locale_for_ireland(self) -> None:
        response = {"jobs": [_CAREERJET_JOB], "total": 1}
        get_mock = MagicMock(return_value=_make_response(json_data=response))
        with (
            patch(
                "job_hunter.sources.boards.careerjet.get_api_config",
                return_value=_CAREERJET_CFG,
            ),
            patch("job_hunter.sources.boards.careerjet.requests.get", get_mock),
        ):
            CareerjetSource().fetch(mk_params(["Software Engineer"], _IE))
        assert get_mock.call_args.kwargs["params"]["locale_code"] == "en_IE"

    def test_fetch_returns_empty_when_no_affid(self) -> None:
        config = {"http": {"job_boards": {"careerjet": {"enabled": True, "affid": ""}}}}
        with patch("job_hunter.sources.boards.careerjet.get_api_config", return_value=config):
            jobs = CareerjetSource().fetch(mk_params(["Software Engineer"], _DE))
        assert jobs == []

    def test_unsupported_country_skips_without_api_call(self) -> None:
        """No silent en_GB fallback: an unsupported country (e.g. BH-only Sudan/SD)
        must skip Careerjet entirely instead of returning UK results."""
        get_mock = MagicMock()
        with (
            patch(
                "job_hunter.sources.boards.careerjet.get_api_config",
                return_value=_CAREERJET_CFG,
            ),
            patch("job_hunter.sources.boards.careerjet.requests.get", get_mock),
        ):
            jobs = CareerjetSource().fetch(
                mk_params(["Software Engineer"], {"sudan": {"country": "SD", "location": "Khartoum"}})
            )
        assert jobs == []
        get_mock.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# Working Nomads
# ═══════════════════════════════════════════════════════════════════════════

_WN_CFG = {"http": {"job_boards": {"workingnomads": {"enabled": True, "timeout_seconds": 10}}}}

_WN_JOB = {
    "title": "Software Engineer",
    "company_name": "NomadCo",
    "url": "https://workingnomads.com/job/1",
    "pub_date": "2026-06-01T00:00:00Z",
    "region": "Worldwide",
    "description": "Work from anywhere.",
}


class TestWorkingNomadsSource:
    def test_name(self) -> None:
        assert WorkingNomadsSource().source_name == "workingnomads"

    def test_is_enabled_false_when_disabled(self) -> None:
        config = {"http": {"job_boards": {"workingnomads": {"enabled": False}}}}
        with patch("job_hunter.sources.source_config.get_api_config", return_value=config):
            assert WorkingNomadsSource().is_enabled(config) is False

    def test_fetch_returns_job_postings(self) -> None:
        with (
            patch(
                "job_hunter.sources.source_config.get_api_config",
                return_value=_WN_CFG,
            ),
            patch(
                "job_hunter.sources.boards.workingnomads.requests.get",
                return_value=_make_response(json_data=[_WN_JOB]),
            ),
        ):
            jobs = WorkingNomadsSource().fetch(mk_params(["Software Engineer"], _DE))
        assert len(jobs) == 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "WorkingNomads"
        assert jobs[0].company == "NomadCo"

    def test_fetch_filters_by_title(self) -> None:
        jobs_data = [
            {**_WN_JOB, "title": "Software Engineer"},
            {**_WN_JOB, "title": "Marketing Manager", "url": "https://workingnomads.com/job/2"},
        ]
        with (
            patch(
                "job_hunter.sources.source_config.get_api_config",
                return_value=_WN_CFG,
            ),
            patch(
                "job_hunter.sources.boards.workingnomads.requests.get",
                return_value=_make_response(json_data=jobs_data),
            ),
        ):
            jobs = WorkingNomadsSource().fetch(mk_params(["Software Engineer"], _DE))
        assert len(jobs) == 1
