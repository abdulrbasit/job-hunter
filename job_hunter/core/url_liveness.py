"""URL liveness checking with an in-process cache."""

from __future__ import annotations

import logging
import threading

import requests

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10
_USER_AGENT = "Mozilla/5.0 (compatible; job-hunter/1.0)"


def url_is_alive(url: str, timeout: int = _DEFAULT_TIMEOUT) -> bool:
    """True if url returns a non-4xx response to a HEAD request."""
    if not url:
        return False
    try:
        resp = requests.head(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        )
        return resp.status_code < 400
    except Exception as exc:
        logger.debug("[url_liveness] %s → error: %s", url, exc)
        return False


class UrlLivenessCache:
    """Per-process cache of URL liveness results. Thread-safe."""

    def __init__(self, checker=None) -> None:
        self._cache: dict[tuple[str, int], bool] = {}
        self._lock = threading.Lock()
        self._checker = checker or url_is_alive

    def is_alive(self, url: str, timeout: int = _DEFAULT_TIMEOUT) -> bool:
        key = (url, timeout)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        result = self._checker(url, timeout)
        with self._lock:
            self._cache[key] = result
        return result
