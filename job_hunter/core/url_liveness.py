"""URL liveness checking with HEAD→GET fallback and an in-process cache.

Many job boards block HEAD (405), or bot-block it (403/429), while GET still
works — so a HEAD failure alone must never mark a URL dead. Check order:

  1. Known ATS direct posting → existing ATS API fetch path (also detects
     closed postings cheaply).
  2. HEAD with redirects: <400 alive; 404/410-style 4xx dead.
  3. On HEAD 403/405/429, 5xx, or exception: lightweight GET. 2xx/3xx bodies
     are checked for closed-posting phrases; 404/410 dead.
  4. GET 403/429 (or GET failing after a HEAD 403/429): the server exists but
     bot-blocks us — treated as ALIVE. Conservative choice: an undetectable
     URL must not drop a good job; downstream enrichment re-checks content.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10
_USER_AGENT = "Mozilla/5.0 (compatible; job-hunter/1.0)"
# HEAD statuses that mean "HEAD is unreliable here, retry with GET" rather than "dead".
_HEAD_RETRY_STATUSES = frozenset({403, 405, 429})
_BOT_BLOCK_STATUSES = frozenset({403, 429})


@dataclass(frozen=True)
class LivenessResult:
    alive: bool
    reason: str
    status_code: int | None = None


def _ats_liveness(url: str, timeout: int) -> LivenessResult | None:
    """ATS direct postings: reuse the existing ATS API fetch path. Returns None
    when the URL is not a recognized ATS posting or the fetch is inconclusive."""
    # Deferred imports keep core free of a module-level dependency on sources.
    from job_hunter.sources.ats_urls import extract_career_url

    if not extract_career_url(url):
        return None
    from job_hunter.sources.jd_fetcher import fetch_jd

    try:
        job = fetch_jd(url, use_llm=False)
    except Exception as exc:
        logger.debug("[url_liveness] ATS fetch error for %s: %s", url, exc)
        return None
    if job is None:
        return None
    if job.get("job_description_fetch_status") == "position_closed":
        return LivenessResult(False, "ats_closed")
    return LivenessResult(True, "ats_ok")


def _get_liveness(url: str, timeout: int, head_status: int | None) -> LivenessResult:
    """Lightweight GET fallback when HEAD was unreliable (403/405/429/5xx/exception)."""
    try:
        resp = requests.get(url, timeout=timeout, allow_redirects=True, headers={"User-Agent": _USER_AGENT})
        status = resp.status_code
        if status in _BOT_BLOCK_STATUSES:
            return LivenessResult(True, f"get_{status}_bot_blocked_assumed_alive", status)
        if status >= 400:
            return LivenessResult(False, f"get_{status}", status)
        from job_hunter.core.utils import strip_html
        from job_hunter.sources.jd_fetcher import _is_posting_inactive

        if _is_posting_inactive(strip_html(resp.text or "")):
            return LivenessResult(False, "closed_posting", status)
        return LivenessResult(True, "get_ok", status)
    except Exception as exc:
        logger.debug("[url_liveness] GET error for %s: %s", url, exc)
        if head_status in _BOT_BLOCK_STATUSES:
            # Server exists but blocks non-browser clients on both verbs.
            return LivenessResult(True, f"head_{head_status}_bot_blocked_assumed_alive", head_status)
        return LivenessResult(False, "request_error", head_status)


def check_url(url: str, timeout: int = _DEFAULT_TIMEOUT) -> LivenessResult:
    """Full liveness check (uncached). See module docstring for the order."""
    if not url:
        return LivenessResult(False, "empty_url")

    ats = _ats_liveness(url, timeout)
    if ats is not None:
        return ats

    head_status: int | None = None
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True, headers={"User-Agent": _USER_AGENT})
        head_status = resp.status_code
        if head_status < 400:
            return LivenessResult(True, "head_ok", head_status)
        if head_status < 500 and head_status not in _HEAD_RETRY_STATUSES:
            return LivenessResult(False, f"head_{head_status}", head_status)
    except Exception as exc:
        logger.debug("[url_liveness] HEAD error for %s: %s", url, exc)

    return _get_liveness(url, timeout, head_status)


def url_is_alive(url: str, timeout: int = _DEFAULT_TIMEOUT) -> bool:
    """Boolean facade over check_url with a debug log of the dead reason."""
    result = check_url(url, timeout)
    if not result.alive:
        logger.info("[url_liveness] dead url=%s reason=%s status=%s", url, result.reason, result.status_code)
    return result.alive


class UrlLivenessCache:
    """Per-process cache of URL liveness results, keyed by canonical URL + timeout. Thread-safe."""

    def __init__(self, checker=None) -> None:
        self._cache: dict[tuple[str, int], LivenessResult] = {}
        self._lock = threading.Lock()
        # Optional bool-returning override (tests / injected checkers).
        self._checker = checker

    def _cache_key(self, url: str, timeout: int) -> tuple[str, int]:
        from job_hunter.sources.search._url_utils import canonicalize_url

        return (canonicalize_url(url) or url, timeout)

    def check(self, url: str, timeout: int = _DEFAULT_TIMEOUT) -> LivenessResult:
        key = self._cache_key(url, timeout)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        if self._checker is not None:
            result = LivenessResult(bool(self._checker(url, timeout)), "custom_checker")
        else:
            result = check_url(url, timeout)
        with self._lock:
            self._cache[key] = result
        return result

    def is_alive(self, url: str, timeout: int = _DEFAULT_TIMEOUT) -> bool:
        return self.check(url, timeout).alive
