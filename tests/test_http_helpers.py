"""Tests for sources/_http.py — fetch_title_pages helper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from job_hunter.sources._http import fetch_title_pages


def _resp(json_data, *, raise_exc=None):
    r = MagicMock()
    if raise_exc:
        r.raise_for_status.side_effect = raise_exc
    else:
        r.raise_for_status = MagicMock()
    r.json.return_value = json_data
    return r


def _terminal_exc(status_code: int):
    """HTTPError whose .response.status_code is terminal (403)."""
    from requests.exceptions import HTTPError

    exc = HTTPError(f"{status_code}")
    exc.response = MagicMock(status_code=status_code)
    return exc


def test_yields_title_and_items_for_single_page():
    items = [{"id": 1}]
    with patch("job_hunter.sources._http.requests.get", return_value=_resp({"jobs": items})):
        results = list(
            fetch_title_pages(
                "https://x.com",
                ["Python"],
                lambda t, p: {},
                "jobs",
                timeout=5,
                max_pages=1,
                source_name="s",
            )
        )
    assert results == [("Python", items)]


def test_stops_on_empty_page():
    pages = iter([_resp({"jobs": [{"id": 1}]}), _resp({"jobs": []})])
    with patch("job_hunter.sources._http.requests.get", side_effect=lambda *a, **kw: next(pages)):
        results = list(
            fetch_title_pages(
                "https://x.com",
                ["Python"],
                lambda t, p: {},
                "jobs",
                timeout=5,
                max_pages=10,
                source_name="s",
            )
        )
    assert len(results) == 1


def test_respects_max_pages():
    call_count = 0

    def fake_get(*a, **kw):
        nonlocal call_count
        call_count += 1
        return _resp({"jobs": [{"id": call_count}]})

    with patch("job_hunter.sources._http.requests.get", side_effect=fake_get):
        list(
            fetch_title_pages(
                "https://x.com",
                ["Python"],
                lambda t, p: {},
                "jobs",
                timeout=5,
                max_pages=2,
                source_name="s",
            )
        )
    assert call_count == 2


def test_terminal_error_stops_all_titles():
    with patch("job_hunter.sources._http.requests.get", return_value=_resp({}, raise_exc=_terminal_exc(403))):
        results = list(
            fetch_title_pages(
                "https://x.com",
                ["Python", "Go"],
                lambda t, p: {},
                "jobs",
                timeout=5,
                max_pages=3,
                source_name="s",
            )
        )
    assert results == []


def test_non_terminal_error_skips_title():
    items = [{"id": 1}]
    call_n = 0

    def fake_get(*a, **kw):
        nonlocal call_n
        call_n += 1
        if call_n == 1:
            raise ConnectionError("transient")
        return _resp({"jobs": items})

    with patch("job_hunter.sources._http.requests.get", side_effect=fake_get):
        results = list(
            fetch_title_pages(
                "https://x.com",
                ["Python", "Go"],
                lambda t, p: {},
                "jobs",
                timeout=5,
                max_pages=1,
                source_name="s",
            )
        )
    assert len(results) == 1
    assert results[0][0] == "Go"


def test_extract_key_none_treats_response_as_list():
    items = [{"id": 1}, {"id": 2}]
    with patch("job_hunter.sources._http.requests.get", return_value=_resp(items)):
        results = list(
            fetch_title_pages(
                "https://x.com",
                ["Python"],
                lambda t, p: {},
                None,
                timeout=5,
                max_pages=1,
                source_name="s",
            )
        )
    assert results == [("Python", items)]
