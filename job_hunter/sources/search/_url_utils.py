"""URL canonicalization and matching helpers."""

from __future__ import annotations

from html import unescape
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from job_hunter.sources.search._constants import (
    JOB_HINTS,
    TRACKING_QUERY_KEYS,
    TRACKING_QUERY_PREFIXES,
)


def _with_scheme(url: str) -> str:
    if url.startswith(("http://", "https://")):
        return url
    return f"https://{url}"


def canonicalize_url(url: str) -> str:
    """Normalize URLs for dedupe while preserving meaningful path/query data."""
    if not url:
        return ""
    parsed = urlparse(_with_scheme(url.strip()))
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or "/"
    query_items = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        key_lower = key.lower()
        if key_lower in TRACKING_QUERY_KEYS:
            continue
        if any(key_lower.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES):
            continue
        query_items.append((key, value))
    query = urlencode(sorted(query_items), doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def _text(value: object) -> str:
    return unescape(str(value or "")).strip()


def _looks_like_job_url(url: str) -> bool:
    lower = url.lower()
    return any(hint in lower for hint in JOB_HINTS)


def _location_match(text: str, location: str) -> bool:
    if not location:
        return True
    lower = text.lower()
    location = location.lower()
    if location in lower:
        return True
    if "remote" in location and "remote" in lower:
        return True
    return False
