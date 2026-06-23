from job_hunter.core.url_liveness import UrlLivenessCache


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
