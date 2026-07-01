"""Tests for sources/job_boards.py — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

import pytest
from conftest import mk_params

from job_hunter.core import api_budget
from job_hunter.models import JobPosting
from job_hunter.sources import job_boards
from job_hunter.sources.job_boards import ArbeitnowSource, JSearchSource


def _make_response(json_data=None, text=None, status_code=200, raise_error=False):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data if json_data is not None else {}
    if raise_error:
        resp.raise_for_status.side_effect = job_boards.requests.exceptions.HTTPError(response=resp)
    else:
        resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture(autouse=True)
def reset_jsearch_failure_state():
    job_boards._JSEARCH_FAILURES = 0
    yield
    job_boards._JSEARCH_FAILURES = 0


ARBEITNOW_JOB = {
    "slug": "pm-berlin-testco",
    "company_name": "TestCo",
    "title": "Product Manager",
    "description": "<p>Great PM role in Berlin.</p>",
    "tags": ["product", "berlin"],
    "job_types": ["full-time"],
    "location": "Berlin, Germany",
    "remote": False,
    "url": "https://www.arbeitnow.com/jobs/testco/product-manager-berlin",
    "created_at": 1745000000,
}

ARBEITNOW_PAGE = {"data": [ARBEITNOW_JOB], "links": {}, "meta": {}}
ARBEITNOW_EMPTY = {"data": [], "links": {}, "meta": {}}

JSEARCH_JOB = {
    "employer_name": "TestCo",
    "job_title": "Product Manager",
    "job_apply_link": "https://linkedin.com/jobs/view/12345",
    "job_description": "Great PM role.",
    "job_city": "Berlin",
    "job_country": "DE",
    "job_posted_at_datetime_utc": "2026-04-01T00:00:00.000Z",
}

JSEARCH_RESPONSE = {"status": "OK", "data": [JSEARCH_JOB]}


# ── ArbeitnowSource ──────────────────────────────────────────────────────────

_ENABLED_ARBEITNOW_CFG = {"http": {"job_boards": {"arbeitnow": {"enabled": True}}}}
_REGIONS = {"DE": {"location": "Berlin", "country": "DE"}}
_CONFIG = {"exclusions": {"title_terms": []}}


class TestArbeitnowSource:
    def test_name(self) -> None:
        assert ArbeitnowSource().source_name == "arbeitnow"

    def test_is_enabled_respects_config(self) -> None:
        disabled_config = {"http": {"job_boards": {"arbeitnow": {"enabled": False}}}}
        with patch("job_hunter.sources.job_boards.get_api_config", return_value=disabled_config):
            assert ArbeitnowSource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self) -> None:
        with (
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                return_value=_make_response(json_data=ARBEITNOW_PAGE),
            ),
        ):
            postings = ArbeitnowSource().fetch(mk_params(["Product Manager"], _REGIONS))
        assert len(postings) == 1
        assert isinstance(postings[0], JobPosting)
        assert postings[0].source == "Arbeitnow"
        assert postings[0].region == "DE"

    def test_fetch_returns_empty_when_disabled(self) -> None:
        disabled_config = {"http": {"job_boards": {"arbeitnow": {"enabled": False}}}}
        with patch("job_hunter.sources.job_boards.get_api_config", return_value=disabled_config):
            postings = ArbeitnowSource().fetch(mk_params(["Product Manager"], _REGIONS))
        assert postings == []

    def test_fetch_filters_by_title_and_location(self) -> None:
        with (
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                return_value=_make_response(json_data=ARBEITNOW_PAGE),
            ),
        ):
            postings = ArbeitnowSource().fetch(mk_params(["Product Owner"], _REGIONS))
        assert postings == []

    def test_fetch_returns_correct_fields(self) -> None:
        with (
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                return_value=_make_response(json_data=ARBEITNOW_PAGE),
            ),
        ):
            postings = ArbeitnowSource().fetch(mk_params(["Product Manager"], _REGIONS))
        posting = postings[0]
        assert posting.company == "TestCo"
        assert posting.url == ARBEITNOW_JOB["url"]
        assert "Berlin" in posting.snippet

    def test_fetch_strips_html(self) -> None:
        with (
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                return_value=_make_response(json_data=ARBEITNOW_PAGE),
            ),
        ):
            postings = ArbeitnowSource().fetch(mk_params(["Product Manager"], _REGIONS))
        assert "<p>" not in postings[0].snippet

    def test_fetch_parses_unix_timestamp(self) -> None:
        with (
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                return_value=_make_response(json_data=ARBEITNOW_PAGE),
            ),
        ):
            postings = ArbeitnowSource().fetch(mk_params(["Product Manager"], _REGIONS))
        assert postings[0].posted_date_text != ""
        assert len(postings[0].posted_date_text) == 10

    def test_fetch_parses_iso_date(self) -> None:
        job = {**ARBEITNOW_JOB, "created_at": "2026-04-15T10:00:00Z"}
        with (
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                return_value=_make_response(json_data={"data": [job]}),
            ),
        ):
            postings = ArbeitnowSource().fetch(mk_params(["Product Manager"], _REGIONS))
        assert postings[0].posted_date_text == "2026-04-15"

    def test_fetch_uses_code_owned_single_page_cap(self) -> None:
        with (
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                return_value=_make_response(json_data=ARBEITNOW_PAGE),
            ) as mock_get,
        ):
            postings = ArbeitnowSource().fetch(mk_params(["Product Manager"], _REGIONS))
        assert len(postings) == 1
        assert mock_get.call_count == 1

    def test_fetch_returns_empty_on_api_error(self) -> None:
        with (
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                side_effect=Exception("timeout"),
            ),
        ):
            postings = ArbeitnowSource().fetch(mk_params(["Product Manager"], _REGIONS))
        assert postings == []


# ── JSearchSource ─────────────────────────────────────────────────────────────

_ENABLED_JSEARCH_CFG = {"http": {"job_boards": {"jsearch": {"enabled": True, "num_pages": 1}}}}


class TestJSearchSource:
    def test_name(self) -> None:
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        assert src.source_name == "jsearch"

    def test_is_enabled_false_without_key(self) -> None:
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = ""
        assert src.is_enabled({}) is False

    def test_fetch_returns_empty_without_key(self) -> None:
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = ""
        postings = src.fetch(mk_params(["Product Manager"], _REGIONS))
        assert postings == []

    def test_fetch_returns_job_postings(self, tmp_path) -> None:
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        import job_hunter.core.api_budget as _budget

        with (
            patch.object(_budget, "ROOT", tmp_path),
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                return_value=_make_response(json_data=JSEARCH_RESPONSE),
            ),
        ):
            postings = src.fetch(mk_params(["Product Manager"], _REGIONS))
        assert len(postings) == 1
        assert isinstance(postings[0], JobPosting)
        assert postings[0].source == "JSearch"
        assert postings[0].region == "DE"

    def test_fetch_returns_empty_when_disabled(self) -> None:
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        disabled_config = {"http": {"job_boards": {"jsearch": {"enabled": False}}}}
        with patch("job_hunter.sources.job_boards.get_api_config", return_value=disabled_config):
            postings = src.fetch(mk_params(["Product Manager"], _REGIONS))
        assert postings == []

    def test_fetch_returns_correct_fields(self) -> None:
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        with (
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                return_value=_make_response(json_data=JSEARCH_RESPONSE),
            ),
        ):
            postings = src.fetch(mk_params(["Product Manager"], _REGIONS))
        posting = postings[0]
        assert posting.company == "TestCo"
        assert posting.url == "https://linkedin.com/jobs/view/12345"
        assert posting.posted_date_text == "2026-04-01"
        assert "Berlin" in posting.snippet

    def test_fetch_includes_location_in_query(self) -> None:
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        with (
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                return_value=_make_response(json_data=JSEARCH_RESPONSE),
            ) as mock_get,
        ):
            src.fetch(mk_params(["Product Manager"], _REGIONS))
        call_params = mock_get.call_args[1]["params"]
        assert "Berlin" in call_params["query"]

    def test_fetch_uses_country_and_language(self) -> None:
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        regions_with_lang = {"DE": {"location": "Berlin", "country": "DE", "search_lang": "en"}}
        with (
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                return_value=_make_response(json_data=JSEARCH_RESPONSE),
            ) as mock_get,
        ):
            src.fetch(mk_params(["Product Manager"], regions_with_lang))
        call_params = mock_get.call_args[1]["params"]
        assert call_params["country"] == "de"
        assert call_params["language"] == "en"

    def test_fetch_excludes_terms(self) -> None:
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        job = {**JSEARCH_JOB, "job_title": "Product Engineer"}
        with (
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                return_value=_make_response(json_data={"status": "OK", "data": [job]}),
            ) as mock_get,
        ):
            postings = src.fetch(
                mk_params(
                    ["Product Manager"],
                    _REGIONS,
                    excluded_title_terms=["engineer", "working student"],
                )
            )
        assert postings == []
        call_params = mock_get.call_args[1]["params"]
        assert '-"engineer"' in call_params["query"]
        assert '-"working student"' in call_params["query"]

    def test_fetch_one_request_per_title(self) -> None:
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        with (
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                return_value=_make_response(json_data=JSEARCH_RESPONSE),
            ) as mock_get,
        ):
            src.fetch(mk_params(["Product Manager", "Product Owner"], _REGIONS))
        assert mock_get.call_count == 2

    def test_fetch_handles_missing_city(self) -> None:
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        job = {**JSEARCH_JOB, "job_city": None, "job_country": None}
        with (
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                return_value=_make_response(json_data={"status": "OK", "data": [job]}),
            ),
        ):
            postings = src.fetch(mk_params(["Product Manager"], _REGIONS))
        assert len(postings) == 1
        assert postings[0].snippet == job["job_description"]

    def test_fetch_suppressed_after_failures(self, reset_jsearch_failure_state) -> None:
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        config = {
            "http": {
                "job_boards": {
                    "max_consecutive_failures": 3,
                    "jsearch": {"enabled": True, "num_pages": 1},
                }
            }
        }
        with (
            patch("job_hunter.sources.job_boards.get_api_config", return_value=config),
            patch("job_hunter.sources.job_boards.requests.get", side_effect=Exception("limit")) as mock_get,
        ):
            for _ in range(4):
                postings = src.fetch(mk_params(["Product Manager"], _REGIONS))
                assert postings == []
        assert mock_get.call_count == 3

    def test_fetch_resets_failure_count(self) -> None:
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        job_boards._JSEARCH_FAILURES = 2
        with (
            patch(
                "job_hunter.sources.job_boards.get_api_config",
                return_value=_ENABLED_JSEARCH_CFG,
            ),
            patch(
                "job_hunter.sources.job_boards.requests.get",
                return_value=_make_response(json_data=JSEARCH_RESPONSE),
            ),
        ):
            postings = src.fetch(mk_params(["Product Manager"], _REGIONS))
        assert len(postings) == 1
        assert job_boards._JSEARCH_FAILURES == 0

    def test_fetch_budget_cap_skips_http(self, monkeypatch: pytest.MonkeyPatch) -> None:
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        monkeypatch.setattr(job_boards, "reserve_api_call", lambda _provider: False)
        monkeypatch.setattr(
            job_boards.requests,
            "get",
            lambda *args, **kwargs: pytest.fail("HTTP should not run"),
        )
        with patch(
            "job_hunter.sources.job_boards.get_api_config",
            return_value=_ENABLED_JSEARCH_CFG,
        ):
            postings = src.fetch(mk_params(["Product Manager"], _REGIONS))
        assert postings == []

    def test_fetch_quota_error_disables(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        src = JSearchSource.__new__(JSearchSource)
        src._rapidapi_key = "test-key"
        monkeypatch.setattr(api_budget, "ROOT", tmp_path)
        calls = {"count": 0}

        def fake_get(*args, **kwargs):
            calls["count"] += 1
            return _make_response(json_data={}, text="Monthly quota exceeded", status_code=429, raise_error=True)

        monkeypatch.setattr(job_boards.requests, "get", fake_get)

        with patch(
            "job_hunter.sources.job_boards.get_api_config",
            return_value=_ENABLED_JSEARCH_CFG,
        ):
            assert src.fetch(mk_params(["Product Manager"], _REGIONS)) == []
            assert src.fetch(mk_params(["Product Manager"], _REGIONS)) == []
        assert calls["count"] == 1
