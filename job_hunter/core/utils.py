"""Core string, HTML, and URL utilities."""

from __future__ import annotations

import re

import requests  # noqa: F401 — exposed so tests can patch utils.requests.head


def strip_html(html: str) -> str:
    """Remove HTML tags and decode common entities."""
    if not html:
        return ""
    try:
        import html as _html_mod

        from bs4 import BeautifulSoup

        unescaped = _html_mod.unescape(html)
        soup = BeautifulSoup(unescaped, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text(separator=" ").strip()
        return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    except ImportError:
        pass
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'")
    return re.sub(r"\s+", " ", text).strip()


def _first_title_match(title: str, job_titles: list[str]) -> re.Match[str] | None:
    """Find first occurrence of any job title using word boundaries."""
    matches = []
    for job_title in job_titles:
        tokens = re.findall(r"\w+", job_title.lower())
        if tokens:
            pattern = rf"(?<!\w){r'[\W_]+'.join(map(re.escape, tokens))}(?!\w)"
            if match := re.search(pattern, title):
                matches.append(match)
    return min(matches, key=lambda match: match.start(), default=None)


def _has_exclusion_before_role(
    title: str,
    excluded_terms: list[str],
    role_match: re.Match[str] | None,
) -> bool:
    """Check if excluded terms appear before the matched role."""
    role_end = role_match.end() if role_match else len(title) + 1
    if excluded_terms:
        for term in excluded_terms:
            term = term.strip().lower()
            if not term:
                continue
            excluded = re.search(rf"(?<!\w){re.escape(term)}(?!\w)", title)
            if excluded and excluded.start() < role_end:
                return True
    return False


def title_matches(title: str, job_titles: list[str], excluded_terms: list[str] | None = None) -> bool:
    """True when a target role appears before any excluded occupation or level."""
    if not title:
        return False
    lower = title.lower()
    role_match = _first_title_match(lower, job_titles) if job_titles else None
    if job_titles and not role_match:
        return False
    if not job_titles:
        return True
    return not _has_exclusion_before_role(lower, excluded_terms or [], role_match)


def location_matches(location: str, filter_location: str) -> bool:
    """True if location string contains the filter substring (case-insensitive)."""
    if not filter_location:
        return True
    if not location:
        return False
    return filter_location.lower() in location.lower()


def url_is_alive(url: str, timeout: int = 10) -> bool:
    """Return True if url returns a 2xx/3xx response to a HEAD request."""
    if not url:
        return False
    try:
        import requests

        resp = requests.head(url, timeout=timeout, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        return resp.status_code < 400 or resp.status_code == 403
    except Exception:
        return False
