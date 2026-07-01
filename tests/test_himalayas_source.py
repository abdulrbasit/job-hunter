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


def test_country_matches_no_restrictions() -> None:
    assert hm._country_matches({}, "DE") is True


def test_country_matches_matching() -> None:
    job = {"locationRestrictions": [{"alpha2": "DE"}]}
    assert hm._country_matches(job, "DE") is True


def test_country_matches_string_restriction() -> None:
    job = {"locationRestrictions": ["Germany"]}
    assert hm._country_matches(job, "DE") is True


def test_country_matches_no_match() -> None:
    job = {"locationRestrictions": [{"alpha2": "US"}]}
    assert hm._country_matches(job, "DE") is False


def test_country_matches_string_no_match() -> None:
    job = {"locationRestrictions": ["United States"]}
    assert hm._country_matches(job, "DE") is False


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
