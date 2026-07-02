from job_hunter.core import url_liveness
from job_hunter.core.url_liveness import LivenessResult, UrlLivenessCache


class _Resp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


def _no_ats(monkeypatch) -> None:
    """Force the ATS API path to be inconclusive so HEAD/GET logic is exercised."""
    monkeypatch.setattr(url_liveness, "_ats_liveness", lambda _url, _timeout: None)


def test_head_200_is_alive(monkeypatch) -> None:
    _no_ats(monkeypatch)
    monkeypatch.setattr(url_liveness.requests, "head", lambda *_a, **_k: _Resp(200))

    result = url_liveness.check_url("https://example.com/jobs/1")

    assert result == LivenessResult(True, "head_ok", 200)


def test_head_404_is_dead(monkeypatch) -> None:
    _no_ats(monkeypatch)
    monkeypatch.setattr(url_liveness.requests, "head", lambda *_a, **_k: _Resp(404))

    result = url_liveness.check_url("https://example.com/jobs/1")

    assert result.alive is False
    assert result.status_code == 404


def test_head_405_falls_back_to_get_200(monkeypatch) -> None:
    _no_ats(monkeypatch)
    monkeypatch.setattr(url_liveness.requests, "head", lambda *_a, **_k: _Resp(405))
    monkeypatch.setattr(url_liveness.requests, "get", lambda *_a, **_k: _Resp(200, "Great open role"))

    result = url_liveness.check_url("https://example.com/jobs/1")

    assert result == LivenessResult(True, "get_ok", 200)


def test_head_exception_falls_back_to_get_200(monkeypatch) -> None:
    _no_ats(monkeypatch)

    def boom(*_a, **_k):
        raise RuntimeError("HEAD not supported")

    monkeypatch.setattr(url_liveness.requests, "head", boom)
    monkeypatch.setattr(url_liveness.requests, "get", lambda *_a, **_k: _Resp(200, "Great open role"))

    result = url_liveness.check_url("https://example.com/jobs/1")

    assert result.alive is True


def test_get_200_with_closed_phrase_is_dead(monkeypatch) -> None:
    _no_ats(monkeypatch)
    monkeypatch.setattr(url_liveness.requests, "head", lambda *_a, **_k: _Resp(405))
    monkeypatch.setattr(
        url_liveness.requests,
        "get",
        lambda *_a, **_k: _Resp(200, "Sorry, this position has been filled."),
    )

    result = url_liveness.check_url("https://example.com/jobs/1")

    assert result == LivenessResult(False, "closed_posting", 200)


def test_get_403_after_head_403_is_conservatively_alive(monkeypatch) -> None:
    """Documented choice: 403/429 on both verbs means the server exists but
    bot-blocks us; we cannot determine liveness, so the job is kept."""
    _no_ats(monkeypatch)
    monkeypatch.setattr(url_liveness.requests, "head", lambda *_a, **_k: _Resp(403))
    monkeypatch.setattr(url_liveness.requests, "get", lambda *_a, **_k: _Resp(403))

    result = url_liveness.check_url("https://example.com/jobs/1")

    assert result.alive is True
    assert "bot_blocked" in result.reason


def test_get_404_after_head_500_is_dead(monkeypatch) -> None:
    _no_ats(monkeypatch)
    monkeypatch.setattr(url_liveness.requests, "head", lambda *_a, **_k: _Resp(500))
    monkeypatch.setattr(url_liveness.requests, "get", lambda *_a, **_k: _Resp(404))

    result = url_liveness.check_url("https://example.com/jobs/1")

    assert result == LivenessResult(False, "get_404", 404)


def test_ats_url_with_successful_api_is_alive(monkeypatch) -> None:
    import job_hunter.sources.jd_fetcher as jd_fetcher

    monkeypatch.setattr(jd_fetcher, "fetch_jd", lambda _url, use_llm=True, **_k: {"title": "PM", "snippet": "role"})

    result = url_liveness.check_url("https://boards.greenhouse.io/acme/jobs/123")

    assert result == LivenessResult(True, "ats_ok")


def test_ats_url_with_closed_posting_is_dead(monkeypatch) -> None:
    import job_hunter.sources.jd_fetcher as jd_fetcher

    monkeypatch.setattr(
        jd_fetcher,
        "fetch_jd",
        lambda _url, use_llm=True, **_k: {"job_description_fetch_status": "position_closed"},
    )

    result = url_liveness.check_url("https://boards.greenhouse.io/acme/jobs/123")

    assert result == LivenessResult(False, "ats_closed")


def test_cache_uses_canonical_url_key(monkeypatch) -> None:
    calls = []

    def checker(url: str, timeout: int) -> bool:
        calls.append(url)
        return True

    cache = UrlLivenessCache(checker)

    assert cache.is_alive("https://example.com/jobs/1?utm_source=x", 5) is True
    assert cache.is_alive("https://example.com/jobs/1", 5) is True
    assert len(calls) == 1


def test_url_liveness_cache_reuses_verdict_for_same_timeout() -> None:
    calls = []

    def checker(url: str, timeout: int) -> bool:
        calls.append((url, timeout))
        return True

    cache = UrlLivenessCache(checker)

    assert cache.is_alive("https://example.com/jobs/1", 5) is True
    assert cache.is_alive("https://example.com/jobs/1", 5) is True

    assert calls == [("https://example.com/jobs/1", 5)]


def test_url_liveness_cache_keeps_timeout_specific_verdicts() -> None:
    calls = []

    def checker(url: str, timeout: int) -> bool:
        calls.append((url, timeout))
        return timeout > 3

    cache = UrlLivenessCache(checker)

    assert cache.is_alive("https://example.com/jobs/1", 2) is False
    assert cache.is_alive("https://example.com/jobs/1", 5) is True

    assert calls == [
        ("https://example.com/jobs/1", 2),
        ("https://example.com/jobs/1", 5),
    ]
