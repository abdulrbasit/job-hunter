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


def title_matches(title: str, job_titles: list[str], excluded_terms: list[str] | None = None) -> bool:
    """True if title contains at least one job title keyword and no excluded terms."""
    if not title:
        return False
    lower = title.lower()
    if excluded_terms and any(
        re.search(rf"(?<!\w){re.escape(term.strip().lower())}(?!\w)", lower) for term in excluded_terms if term.strip()
    ):
        return False
    if not job_titles:
        return True
    return any(jt.lower() in lower for jt in job_titles)


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
