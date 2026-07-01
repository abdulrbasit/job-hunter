"""Tests for hh_source (HeadHunter/hh.ru adapter)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from job_hunter.models import SearchParams
from job_hunter.sources.hh_source import _ISO_TO_HH_AREA, HHSource


def _params(country: str = "RU", location: str = "Moscow") -> SearchParams:
    return SearchParams(
        region_key="ru_moscow",
        country=country,
        location=location,
        search_lang="ru",
        job_titles=["Product Manager"],
        excluded_title_terms=[],
    )


def _mock_response(items: list, pages: int = 1) -> MagicMock:
    mock = MagicMock()
    mock.raise_for_status.return_value = None
    mock.json.return_value = {"items": items, "pages": pages}
    return mock


_SAMPLE_ITEM = {
    "name": "Product Manager",
    "alternate_url": "https://hh.ru/vacancy/12345",
    "employer": {"name": "Acme Corp"},
    "area": {"name": "Moscow"},
    "published_at": "2026-06-30T10:00:00+0300",
    "snippet": {"requirement": "3+ years PM experience"},
}


class TestHHSource:
    def test_skips_unmapped_country(self) -> None:
        src = HHSource()
        result = src.fetch(_params(country="DE"))
        assert result == []

    def test_returns_empty_for_empty_items(self) -> None:
        src = HHSource()
        with patch("requests.get", return_value=_mock_response([])):
            result = src.fetch(_params())
        assert result == []

    def test_parses_single_job_correctly(self) -> None:
        src = HHSource()
        with patch("requests.get", return_value=_mock_response([_SAMPLE_ITEM])):
            result = src.fetch(_params())
        assert len(result) == 1
        jp = result[0]
        assert jp.title == "Product Manager"
        assert jp.url == "https://hh.ru/vacancy/12345"
        assert jp.company == "Acme Corp"
        assert jp.location == "Moscow"
        assert jp.posted_date_text == "2026-06-30"
        assert "3+ years PM experience" in jp.snippet
        assert jp.source == "hh.ru"

    def test_filters_by_title(self) -> None:
        item_no_match = {**_SAMPLE_ITEM, "name": "Data Scientist"}
        src = HHSource()
        with patch("requests.get", return_value=_mock_response([_SAMPLE_ITEM, item_no_match])):
            result = src.fetch(_params())
        assert len(result) == 1
        assert result[0].title == "Product Manager"

    def test_paginates_until_pages_exhausted(self) -> None:
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Return 1 item per page; signal 2 total pages
            return _mock_response([_SAMPLE_ITEM], pages=2)

        src = HHSource()
        with patch("requests.get", side_effect=side_effect):
            result = src.fetch(_params())
        # page 0 and page 1 = 2 calls per title
        assert call_count == 2
        assert len(result) == 2

    def test_stops_on_terminal_http_error(self) -> None:
        import requests as req_mod

        mock = MagicMock()
        http_err = req_mod.exceptions.HTTPError(response=MagicMock(status_code=404))
        mock.raise_for_status.side_effect = http_err

        src = HHSource()
        with patch("requests.get", return_value=mock):
            result = src.fetch(_params())
        assert result == []

    def test_all_cis_isos_are_mapped(self) -> None:
        for iso in ("RU", "KZ", "UA", "BY", "AZ", "AM"):
            assert iso in _ISO_TO_HH_AREA, f"{iso} missing from _ISO_TO_HH_AREA"

    def test_source_name(self) -> None:
        assert HHSource().source_name == "hh"
