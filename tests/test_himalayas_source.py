"""Tests for sources/boards/himalayas.py — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

from job_hunter.sources.boards import himalayas as hm


def _mock_get(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


_ENABLED_CFG = {
    "http": {
        "job_boards": {
            "himalayas": {
                "enabled": True,
                "timeout_seconds": 10,
            }
        }
    }
}

_REGIONS = {
    "global_remote": {"country": "DE", "location": ""},
}

_CONFIG = {"exclusions": {"title_terms": []}}

_RESPONSE = {
    "jobs": [
        {
            "title": "Product Manager",
            "companyName": "Remote Corp",
            "applicationLink": "https://himalayas.app/jobs/pm-123",
            "pubDate": 1714521600000,
            "locationRestrictions": [{"alpha2": "DE", "name": "Germany"}],
            "description": "<p>Great remote PM role.</p>",
        },
        {
            "title": "Sales Director",
            "companyName": "Other Co",
            "applicationLink": "https://himalayas.app/jobs/sd-999",
            "pubDate": 1714521600000,
            "locationRestrictions": [{"alpha2": "US", "name": "United States"}],
            "description": "US only.",
        },
    ]
}


def test_posted_from_timestamp() -> None:
    assert hm._posted(1714521600000) == "2024-05-01"


def test_posted_from_string() -> None:
    assert hm._posted("2026-05-01T12:00:00Z") == "2026-05-01"


def test_posted_unknown() -> None:
    assert hm._posted(None) == ""


def test_location_text_remote_fallback() -> None:
    assert hm._location_text({}) == "Remote"


def test_location_text_with_restrictions() -> None:
    job = {"locationRestrictions": [{"alpha2": "DE", "name": "Germany"}]}
    assert hm._location_text(job) == "Germany"


def test_location_text_with_string_restrictions() -> None:
    job = {"locationRestrictions": ["Germany", "United States"]}
    assert hm._location_text(job) == "Germany, United States"


class TestHimalayasSource:
    def test_name(self) -> None:
        assert hm.HimalayasSource().source_name == "himalayas"

    def test_is_enabled_false_when_disabled(self) -> None:
        disabled = {"http": {"job_boards": {"himalayas": {"enabled": False}}}}
        with patch("job_hunter.sources.boards.himalayas.get_api_config", return_value=disabled):
            assert hm.HimalayasSource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self) -> None:
        from job_hunter.models import JobPosting, SearchParams

        params = SearchParams(
            region_key="global_remote",
            country="DE",
            location="",
            search_lang="",
            job_titles=["Product Manager"],
        )
        with (
            patch(
                "job_hunter.sources.boards.himalayas.get_api_config",
                return_value=_ENABLED_CFG,
            ),
            patch(
                "job_hunter.sources._http.requests.get",
                return_value=_mock_get(_RESPONSE),
            ),
        ):
            jobs = hm.HimalayasSource().fetch(params)
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "Himalayas"
        assert jobs[0].location_restrictions == ["Germany"]

    def test_fetch_does_not_early_filter_jobs_restricted_to_other_countries(self) -> None:
        """Himalayas no longer drops a job locally just because locationRestrictions
        name a different country — that decision moves to JobPolicy/quality_gate.
        location_restrictions is still populated so the downstream check has a signal."""
        from job_hunter.models import SearchParams

        params = SearchParams(
            region_key="global_remote",
            country="DE",
            location="",
            search_lang="",
            job_titles=["Product Manager", "Sales Director"],
        )
        with (
            patch(
                "job_hunter.sources.boards.himalayas.get_api_config",
                return_value=_ENABLED_CFG,
            ),
            patch(
                "job_hunter.sources._http.requests.get",
                return_value=_mock_get(_RESPONSE),
            ),
        ):
            jobs = hm.HimalayasSource().fetch(params)
        titles = {job.title for job in jobs}
        assert titles == {"Product Manager", "Sales Director"}
        us_job = next(job for job in jobs if job.title == "Sales Director")
        assert us_job.location_restrictions == ["United States"]
