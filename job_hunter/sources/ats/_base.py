from __future__ import annotations

from job_hunter.config.loader import get_api_config, get_timeout

_TIMEOUT = get_timeout("ats_scraper")
_ATS_CFG = get_api_config().get("http", {}).get("ats_scraper", {}) or {}
_SNIPPET_CHARS = int(_ATS_CFG.get("snippet_chars", 2000))


def _build_snippet(location: str, body: str) -> str:
    body = body[:_SNIPPET_CHARS]
    return f"{location} - {body}" if location else body
