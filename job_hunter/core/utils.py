"""Core string, HTML, URL, and file-reading utilities."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import requests  # noqa: F401 — exposed so tests can patch utils.requests.head


def read_yaml(path: Path) -> Any:
    """Read a YAML file, returning {} if it doesn't exist."""
    import yaml

    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


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


def title_matches_any_role(title: str, job_titles: list[str]) -> bool:
    """True when title contains any of the target roles. Empty job_titles matches everything."""
    if not title:
        return False
    if not job_titles:
        return True
    return _first_title_match(title.lower(), job_titles) is not None


def has_excluded_title_term(title: str, excluded_terms: list[str] | None) -> bool:
    """True when any excluded term appears in title, anywhere, regardless of word order."""
    if not title or not excluded_terms:
        return False
    lower = title.lower()
    for term in excluded_terms:
        term = term.strip().lower()
        if not term:
            continue
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lower):
            return True
    return False


_GENERIC_ROLE_TOKENS = {
    "associate",
    "entry",
    "expert",
    "intern",
    "internship",
    "jr",
    "junior",
    "lead",
    "manager",
    "mid",
    "principal",
    "senior",
    "specialist",
    "staff",
    "student",
    "trainee",
}


def _relaxed_student_title_match(title: str, job_titles: list[str]) -> bool:
    title_tokens = set(re.findall(r"\w+", title.casefold())) - _GENERIC_ROLE_TOKENS
    for target in job_titles:
        target_tokens = set(re.findall(r"\w+", target.casefold())) - _GENERIC_ROLE_TOKENS
        meaningful = {token for token in target_tokens if len(token) >= 3}
        if meaningful and meaningful & title_tokens:
            return True
    return False


def title_is_allowed(
    title: str,
    job_titles: list[str],
    excluded_terms: list[str] | None = None,
    *,
    relaxed_student: bool = False,
) -> bool:
    """True when title matches a target role and carries no excluded term (word-order independent)."""
    if not title_matches_any_role(title, job_titles) and not (
        relaxed_student and _relaxed_student_title_match(title, job_titles)
    ):
        return False
    return not has_excluded_title_term(title, excluded_terms)


def title_matches(title: str, job_titles: list[str], excluded_terms: list[str] | None = None) -> bool:
    """Deprecated alias for title_is_allowed — kept for callers not yet migrated."""
    return title_is_allowed(title, job_titles, excluded_terms)


def location_matches(location: str, filter_location: str) -> bool:
    """True if location string contains the filter substring (case-insensitive)."""
    if not filter_location:
        return True
    if not location:
        return False
    return filter_location.lower() in location.lower()


def url_is_alive(url: str, timeout: int = 10) -> bool:
    """Compatibility alias — job_hunter.core.url_liveness is the single implementation
    (HEAD→GET fallback, bot-block tolerance, closed-posting body check)."""
    from job_hunter.core.url_liveness import url_is_alive as _url_is_alive

    return _url_is_alive(url, timeout)


_CORPORATE_SUFFIX_RE = re.compile(
    r"\b(gmbh|ag|inc|inc\.|ltd|ltd\.|llc|plc|se|sa|s\.a\.|corp|corp\.|corporation|group)\b",
    re.IGNORECASE,
)
_COMPANY_NOISE_SUFFIX_RE = re.compile(
    r"\s+(linkedin jobs|on linkedin|linkedin|careers|job board)$",
    re.IGNORECASE,
)


def normalize_company_name(company: str) -> str:
    """Normalize employer names for stable comparison across source suffixes."""
    company = _COMPANY_NOISE_SUFFIX_RE.sub("", company or "")
    normalized = _CORPORATE_SUFFIX_RE.sub("", company)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower())
    return " ".join(normalized.split())
