"""Tests for sources/boards/arbeitnow.py — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

from conftest import mk_params

from job_hunter.models import JobPosting
from job_hunter.sources.boards.arbeitnow import ArbeitnowSource


def _make_response(json_data=None, text=None, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data if json_data is not None else {}
    resp.raise_for_status = MagicMock()
    return resp


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

_ENABLED_ARBEITNOW_CFG = {"http": {"job_boards": {"arbeitnow": {"enabled": True}}}}
_REGIONS = {"DE": {"location": "Berlin", "country": "DE"}}
_CONFIG = {"exclusions": {"title_terms": []}}


class TestArbeitnowSource:
    def test_name(self) -> None:
        assert ArbeitnowSource().source_name == "arbeitnow"

    def test_is_enabled_respects_config(self) -> None:
        disabled_config = {"http": {"job_boards": {"arbeitnow": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.arbeitnow.get_api_config", return_value=disabled_config):
            assert ArbeitnowSource().is_enabled(disabled_config) is False

    def test_fetch_returns_job_postings(self) -> None:
        with (
            patch(
                "job_hunter.sources.boards.arbeitnow.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.boards.arbeitnow.requests.get",
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
        with patch("job_hunter.sources.boards.arbeitnow.get_api_config", return_value=disabled_config):
            postings = ArbeitnowSource().fetch(mk_params(["Product Manager"], _REGIONS))
        assert postings == []

    def test_fetch_filters_by_title_and_location(self) -> None:
        with (
            patch(
                "job_hunter.sources.boards.arbeitnow.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.boards.arbeitnow.requests.get",
                return_value=_make_response(json_data=ARBEITNOW_PAGE),
            ),
        ):
            postings = ArbeitnowSource().fetch(mk_params(["Product Owner"], _REGIONS))
        assert postings == []

    def test_fetch_returns_correct_fields(self) -> None:
        with (
            patch(
                "job_hunter.sources.boards.arbeitnow.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.boards.arbeitnow.requests.get",
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
                "job_hunter.sources.boards.arbeitnow.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.boards.arbeitnow.requests.get",
                return_value=_make_response(json_data=ARBEITNOW_PAGE),
            ),
        ):
            postings = ArbeitnowSource().fetch(mk_params(["Product Manager"], _REGIONS))
        assert "<p>" not in postings[0].snippet

    def test_fetch_parses_unix_timestamp(self) -> None:
        with (
            patch(
                "job_hunter.sources.boards.arbeitnow.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.boards.arbeitnow.requests.get",
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
                "job_hunter.sources.boards.arbeitnow.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.boards.arbeitnow.requests.get",
                return_value=_make_response(json_data={"data": [job]}),
            ),
        ):
            postings = ArbeitnowSource().fetch(mk_params(["Product Manager"], _REGIONS))
        assert postings[0].posted_date_text == "2026-04-15"

    def test_fetch_uses_code_owned_single_page_cap(self) -> None:
        with (
            patch(
                "job_hunter.sources.boards.arbeitnow.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.boards.arbeitnow.requests.get",
                return_value=_make_response(json_data=ARBEITNOW_PAGE),
            ) as mock_get,
        ):
            postings = ArbeitnowSource().fetch(mk_params(["Product Manager"], _REGIONS))
        assert len(postings) == 1
        assert mock_get.call_count == 1

    def test_fetch_returns_empty_on_api_error(self) -> None:
        with (
            patch(
                "job_hunter.sources.boards.arbeitnow.get_api_config",
                return_value=_ENABLED_ARBEITNOW_CFG,
            ),
            patch(
                "job_hunter.sources.boards.arbeitnow.requests.get",
                side_effect=Exception("timeout"),
            ),
        ):
            postings = ArbeitnowSource().fetch(mk_params(["Product Manager"], _REGIONS))
        assert postings == []
