"""Tests for sources/arbeitsagentur_source.py — all HTTP calls are mocked."""

from unittest.mock import MagicMock, patch

from job_hunter.sources import arbeitsagentur_source as aa


def _mock_get(json_data, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json.return_value = json_data
    return resp


_ENABLED_CFG = {
    "http": {
        "job_boards": {
            "arbeitsagentur": {
                "enabled": True,
                "timeout_seconds": 10,
                "results_per_query": 25,
            }
        }
    }
}

_REGIONS = {
    "berlin": {"country": "DE", "location": "Berlin"},
}

_CONFIG = {"exclusions": {"title_terms": []}}

_RESPONSE = {
    "stellenangebote": [
        {
            "titel": "Product Manager",
            "arbeitgeber": "Acme GmbH",
            "refnr": "BA-12345",
            "aktuelleVeroeffentlichungsdatum": "2026-05-01T00:00:00",
            "arbeitsort": {"ort": "Berlin", "land": "Deutschland"},
            "stellenbeschreibung": "Great role.",
        },
        {
            "titel": "Sales Manager",
            "arbeitgeber": "Other GmbH",
            "refnr": "BA-99999",
            "aktuelleVeroeffentlichungsdatum": "2026-05-02T00:00:00",
            "arbeitsort": {"ort": "Munich", "land": "Deutschland"},
            "stellenbeschreibung": "Munich role.",
        },
    ]
}


class TestArbeitsagenturSource:
    def test_name(self) -> None:
        assert aa.ArbeitsagenturSource().name == "arbeitsagentur"

    def test_is_enabled_false_when_disabled(self) -> None:
        disabled = {"http": {"job_boards": {"arbeitsagentur": {"enabled": False}}}}
        with patch("job_hunter.sources.arbeitsagentur_source.load_api_config", return_value=disabled):
            assert aa.ArbeitsagenturSource().is_enabled({}) is False

    def test_fetch_returns_job_postings(self) -> None:
        from job_hunter.models import JobPosting, SearchParams

        params = SearchParams(
            region_key="berlin",
            country="DE",
            location="Berlin",
            search_lang="de",
            job_titles=["Product Manager"],
        )
        with (
            patch(
                "job_hunter.sources.arbeitsagentur_source.load_api_config",
                return_value=_ENABLED_CFG,
            ),
            patch(
                "job_hunter.sources.arbeitsagentur_source.requests.get",
                return_value=_mock_get(_RESPONSE),
            ),
        ):
            jobs = aa.ArbeitsagenturSource().fetch(params)
        assert len(jobs) >= 1
        assert isinstance(jobs[0], JobPosting)
        assert jobs[0].source == "Arbeitsagentur"
