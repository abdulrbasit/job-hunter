"""Tests for new job source modules — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

from conftest import mk_params

from job_hunter.models import JobPosting
from job_hunter.sources.boards.adzuna import AdzunaSource
from job_hunter.sources.boards.careerjet import CareerjetSource
from job_hunter.sources.boards.gulftalent import GulfTalentSource
from job_hunter.sources.boards.jobbank import JobBankSource
from job_hunter.sources.boards.jobicy import JobicySource
from job_hunter.sources.boards.jobstreet import JobStreetSource
from job_hunter.sources.boards.jooble import JoobleSource
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
            assert JobicySource().is_enabled({}) is False

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
            assert RemoteOKSource().is_enabled({}) is False

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


# ═══════════════════════════════════════════════════════════════════════════
# Jooble
# ═══════════════════════════════════════════════════════════════════════════

_JOOBLE_CFG = {"http": {"job_boards": {"jooble": {"enabled": True, "timeout_seconds": 10}}}}

_JOOBLE_JOB = {
    "title": "Software Engineer",
    "company": "JoobleCo",
    "link": "https://jooble.org/1",
    "updated": "2026-06-01",
    "location": "Berlin",
    "snippet": "A great role.",
}


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

_GT_HTML = """<html><body>
<div class="job-listing">
  <h2><a class="job-title" href="/jobs/456">Product Manager</a></h2>
  <span class="company-name">GulfCorp</span>
  <span class="location">Dubai, UAE</span>
</div></body></html>"""

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
            assert GulfTalentSource().is_enabled({}) is False

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


class TestJobBankSource:
    def test_name(self) -> None:
        assert JobBankSource().source_name == "jobbank"

    def test_is_enabled_false_when_disabled(self) -> None:
        disabled = {"http": {"job_boards": {"jobbank": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.jobbank.get_api_config", return_value=disabled):
            assert JobBankSource().is_enabled({}) is False

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
            assert JobStreetSource().is_enabled({}) is False

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


class TestMyCareersFutureSource:
    def test_name(self) -> None:
        assert MyCareersFutureSource().source_name == "mycareersfuture"

    def test_is_enabled_false_when_disabled(self) -> None:
        disabled = {"http": {"job_boards": {"mycareersfuture": {"enabled": False}}}}
        with patch(
            "job_hunter.sources.boards.mycareersfuture.get_api_config",
            return_value=disabled,
        ):
            assert MyCareersFutureSource().is_enabled({}) is False

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
            assert WeWorkRemotelySource().is_enabled({}) is False

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
            assert src.is_enabled({}) is False

    def test_fetch_returns_job_postings(self) -> None:
        src = ReedSource.__new__(ReedSource)
        src._api_key = "test-key"
        cfg = {"http": {"job_boards": {"reed": {"enabled": True, "results_wanted": 1}}}}
        page_data = {"results": [_REED_JOB(1)]}
        with (
            patch("job_hunter.sources.boards.reed.get_api_config", return_value=cfg),
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
            assert src.is_enabled({}) is False

    def test_fetch_returns_job_postings(self) -> None:
        src = AdzunaSource.__new__(AdzunaSource)
        src._app_id = "app123"
        src._api_key = "key123"
        cfg = {"http": {"job_boards": {"adzuna": {"enabled": True, "results_per_page": 1}}}}
        page_data = {"results": [_ADZUNA_JOB(1)]}
        with (
            patch("job_hunter.sources.boards.adzuna.get_api_config", return_value=cfg),
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


class TestJoobleSource:
    def test_name(self) -> None:
        src = JoobleSource.__new__(JoobleSource)
        src._api_key = "test-key"
        assert src.source_name == "jooble"

    def test_is_enabled_false_when_disabled(self) -> None:
        src = JoobleSource.__new__(JoobleSource)
        src._api_key = "test-key"
        disabled = {"http": {"job_boards": {"jooble": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.jooble.get_api_config", return_value=disabled):
            assert src.is_enabled({}) is False

    def test_fetch_returns_job_postings(self) -> None:
        src = JoobleSource.__new__(JoobleSource)
        src._api_key = "test-key"
        with (
            patch(
                "job_hunter.sources.boards.jooble.get_api_config",
                return_value=_JOOBLE_CFG,
            ),
            patch("job_hunter.sources.boards.jooble.reserve_api_call", return_value=True),
            patch(
                "job_hunter.sources.boards.jooble.requests.post",
                return_value=_make_response(json_data={"jobs": [_JOOBLE_JOB]}),
            ),
        ):
            jobs = src.fetch(mk_params(["Software Engineer"], _REGIONS))
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "Jooble"


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
        cfg = {"http": {"job_boards": {"careerjet": {"enabled": True, "affid": ""}}}}
        with patch("job_hunter.sources.boards.careerjet.get_api_config", return_value=cfg):
            assert CareerjetSource().is_enabled({}) is False

    def test_is_enabled_false_when_disabled(self) -> None:
        cfg = {"http": {"job_boards": {"careerjet": {"enabled": False, "affid": "x"}}}}
        with patch("job_hunter.sources.boards.careerjet.get_api_config", return_value=cfg):
            assert CareerjetSource().is_enabled({}) is False

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
        cfg = {"http": {"job_boards": {"careerjet": {"enabled": True, "affid": ""}}}}
        with patch("job_hunter.sources.boards.careerjet.get_api_config", return_value=cfg):
            jobs = CareerjetSource().fetch(mk_params(["Software Engineer"], _DE))
        assert jobs == []


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
        cfg = {"http": {"job_boards": {"workingnomads": {"enabled": False}}}}
        with patch("job_hunter.sources.source_config.get_api_config", return_value=cfg):
            assert WorkingNomadsSource().is_enabled({}) is False

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
