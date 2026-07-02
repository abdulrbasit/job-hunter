"""Tests for sources/boards/remotive.py — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

from conftest import mk_params

from job_hunter.models import JobPosting
from job_hunter.sources.boards.remotive import RemotiveSource


def _mock_get(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


_ENABLED_CFG = {
    "http": {
        "job_boards": {
            "remotive": {
                "enabled": True,
                "timeout_seconds": 10,
            }
        }
    }
}

_REGIONS = {
    "EU": {"location": "Europe", "country": "DE"},
}

_CONFIG = {"exclusions": {"title_terms": []}}


class TestRemotiveSource:
    def test_name(self) -> None:
        assert RemotiveSource().source_name == "remotive"

    def test_is_enabled_respects_config(self) -> None:
        disabled_config = {"http": {"job_boards": {"remotive": {"enabled": False}}}}
        with patch(
            "job_hunter.sources.source_config.get_api_config",
            return_value=disabled_config,
        ):
            assert RemotiveSource().is_enabled(disabled_config) is False

    def test_fetch_returns_job_postings(self) -> None:
        response_data = {
            "jobs": [
                {
                    "title": "Software Engineer",
                    "company_name": "ACME",
                    "url": "https://example.com/job/1",
                    "publication_date": "2026-06-01",
                    "candidate_required_location": "Remote",
                    "description": "<p>Some job</p>",
                }
            ]
        }
        with (
            patch(
                "job_hunter.sources.source_config.get_api_config",
                return_value=_ENABLED_CFG,
            ),
            patch(
                "job_hunter.sources._http.requests.get",
                return_value=MagicMock(raise_for_status=MagicMock(), **{"json.return_value": response_data}),
            ),
        ):
            jobs = RemotiveSource().fetch(mk_params(["Software Engineer"], _REGIONS))
        assert len(jobs) == 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].title == "Software Engineer"
        assert jobs[0].source == "Remotive"

    def test_fetch_returns_empty_when_disabled(self) -> None:
        disabled_config = {"http": {"job_boards": {"remotive": {"enabled": False}}}}
        with patch(
            "job_hunter.sources.source_config.get_api_config",
            return_value=disabled_config,
        ):
            jobs = RemotiveSource().fetch(mk_params(["Software Engineer"], _REGIONS))
        assert jobs == []
