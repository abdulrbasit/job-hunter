from __future__ import annotations

import pytest

from job_hunter.sources import scraper as scraper_module
from job_hunter.sources.scraper import _boards as scraper_boards
from job_hunter.sources.scraper import _discovery as scraper_discovery
from job_hunter.sources.search_providers import preflight


class Response:
    def __init__(self, status_code: int = 200, payload=None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = {} if payload is None else payload
        self.text = text
        self.content = text.encode("utf-8") if text else b"<rss />"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            exc = RuntimeError(f"{self.status_code} Client Error")
            exc.response = self
            raise exc

    def json(self):
        return self._payload


def _api_cfg_for(source: str) -> dict:
    boards = {name: {"enabled": False} for name in preflight._source_probes()}
    boards[source] = {"enabled": True}
    return {"http": {"job_boards": boards}}


def test_job_source_preflight_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight, "load_api_config", lambda: _api_cfg_for("arbeitnow"))
    monkeypatch.setattr(
        preflight.requests,
        "get",
        lambda *args, **kwargs: Response(payload={"data": []}),
    )

    results = preflight.probe_job_sources(
        ["Product Manager"],
        {"berlin": {"country": "DE", "location": "Berlin"}},
        {},
    )

    assert results["arbeitnow"].status == "ok"


def test_job_source_preflight_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight, "load_api_config", lambda: _api_cfg_for("jooble"))
    monkeypatch.setattr(preflight, "JOOBLE_API_KEY", "")

    results = preflight.probe_job_sources(
        ["Product Manager"],
        {"berlin": {"country": "DE", "location": "Berlin"}},
        {},
    )

    assert results["jooble"].status == "missing_key"


def test_job_source_preflight_quota_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    exhausted: list[str] = []
    monkeypatch.setattr(preflight, "load_api_config", lambda: _api_cfg_for("jooble"))
    monkeypatch.setattr(preflight, "JOOBLE_API_KEY", "key")
    monkeypatch.setattr(
        preflight,
        "mark_api_exhausted",
        lambda provider, **_kwargs: exhausted.append(provider),
    )
    monkeypatch.setattr(
        preflight.requests,
        "post",
        lambda *args, **kwargs: Response(status_code=402, text="Payment Required"),
    )

    results = preflight.probe_job_sources(
        ["Product Manager"],
        {"berlin": {"country": "DE", "location": "Berlin"}},
        {},
    )

    assert results["jooble"].status == "quota_exhausted"
    assert exhausted == ["jooble"]


def test_job_source_preflight_plain_429_is_run_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preflight, "load_api_config", lambda: _api_cfg_for("arbeitnow"))
    monkeypatch.setattr(
        preflight.requests,
        "get",
        lambda *args, **kwargs: Response(status_code=429, text="Too Many Requests"),
    )

    results = preflight.probe_job_sources(
        ["Product Manager"],
        {"berlin": {"country": "DE", "location": "Berlin"}},
        {},
    )

    assert results["arbeitnow"].status == "rate_limited"


def test_job_source_preflight_plain_403_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preflight, "load_api_config", lambda: _api_cfg_for("arbeitnow"))
    monkeypatch.setattr(
        preflight.requests,
        "get",
        lambda *args, **kwargs: Response(status_code=403, text="Forbidden"),
    )

    results = preflight.probe_job_sources(
        ["Product Manager"],
        {"berlin": {"country": "DE", "location": "Berlin"}},
        {},
    )

    assert results["arbeitnow"].status == "blocked"


def test_job_source_preflight_malformed_response_is_broken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preflight, "load_api_config", lambda: _api_cfg_for("arbeitnow"))
    monkeypatch.setattr(preflight.requests, "get", lambda *args, **kwargs: Response(payload=[]))

    results = preflight.probe_job_sources(
        ["Product Manager"],
        {"berlin": {"country": "DE", "location": "Berlin"}},
        {},
    )

    assert results["arbeitnow"].status == "broken"


def test_scrape_skips_disabled_source(monkeypatch: pytest.MonkeyPatch) -> None:
    disabled = {name: preflight.SourceProbeResult(name, "disabled", "test") for name in preflight._source_probes()}
    disabled["jobicy"] = preflight.SourceProbeResult("jobicy", "broken", "test")

    monkeypatch.setattr(scraper_boards, "load_search_config", lambda: {"regions": {}})
    monkeypatch.setattr(scraper_boards, "probe_search_providers", lambda: set())
    monkeypatch.setattr(scraper_boards, "set_run_disabled", lambda _disabled: None)
    monkeypatch.setattr(scraper_boards, "probe_job_sources", lambda *_args: disabled)
    monkeypatch.setattr(scraper_discovery, "discover_ats_jobs_by_search", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        scraper_boards.JobicySource,
        "fetch",
        lambda *args, **kwargs: pytest.fail("disabled Jobicy should not run"),
    )

    assert scraper_module.scrape() == []
