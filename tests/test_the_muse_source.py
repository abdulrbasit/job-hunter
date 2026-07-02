"""Tests for sources/boards/the_muse.py — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

from conftest import mk_params

from job_hunter.sources.boards.the_muse import TheMuseSource


def _mock_get(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


_ENABLED_CFG = {
    "http": {
        "job_boards": {
            "the_muse": {
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


class TestTheMuseSource:
    def test_name(self) -> None:
        assert TheMuseSource().source_name == "the_muse"

    def test_is_enabled_false_when_disabled(self) -> None:
        disabled = {"http": {"job_boards": {"the_muse": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.the_muse.get_api_config", return_value=disabled):
            assert TheMuseSource().is_enabled(disabled) is False

    def test_fetch_returns_job_postings(self) -> None:
        from job_hunter.models import JobPosting

        response_data = {
            "results": [
                {
                    "name": "Software Engineer",
                    "company": {"name": "MuseCo"},
                    "refs": {"landing_page": "https://www.themuse.com/jobs/museco/swe"},
                    "publication_date": "2026-06-01T00:00:00Z",
                    "locations": [{"name": "Remote"}],
                    "contents": "Build great things.",
                }
            ]
        }
        with (
            patch(
                "job_hunter.sources.boards.the_muse.get_api_config",
                return_value=_ENABLED_CFG,
            ),
            patch(
                "job_hunter.sources.boards.the_muse.requests.get",
                return_value=_mock_get(response_data),
            ),
        ):
            jobs = TheMuseSource().fetch(mk_params(["Software Engineer"], _REGIONS))
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "The Muse"

    def test_fetch_does_not_early_filter_jobs_outside_region_location(self) -> None:
        """The Muse no longer drops a job locally just because its location doesn't
        match the region — that decision moves to JobPolicy/quality_gate downstream.
        location_restrictions is now populated so the downstream check has a signal."""
        from job_hunter.models import JobPosting

        response_data = {
            "results": [
                {
                    "name": "Software Engineer",
                    "company": {"name": "MuseCo"},
                    "refs": {"landing_page": "https://www.themuse.com/jobs/museco/swe"},
                    "publication_date": "2026-06-01T00:00:00Z",
                    "locations": [{"name": "San Francisco, CA"}],
                    "contents": "Build great things.",
                }
            ]
        }
        with (
            patch(
                "job_hunter.sources.boards.the_muse.get_api_config",
                return_value=_ENABLED_CFG,
            ),
            patch(
                "job_hunter.sources.boards.the_muse.requests.get",
                return_value=_mock_get(response_data),
            ),
        ):
            jobs = TheMuseSource().fetch(mk_params(["Software Engineer"], _REGIONS))
        assert len(jobs) == 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].location == "San Francisco, CA"
        assert jobs[0].location_restrictions == ["San Francisco, CA"]
