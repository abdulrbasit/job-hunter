"""Shared ATS URL parsing helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class AtsCareerPattern:
    name: str
    pattern: str
    career_template: str
    api_template: str = ""
    discovery_site_query: str = ""
    discovery_host_pattern: str = ""
    discovery_path_pattern: str = ""


ATS_CAREER_PATTERNS: tuple[AtsCareerPattern, ...] = (
    AtsCareerPattern(
        "greenhouse",
        r"(?:boards|job-boards)\.greenhouse\.io/([^/?#]+)",
        "boards.greenhouse.io/{0}",
        "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
        "site:boards.greenhouse.io OR site:job-boards.greenhouse.io",
        r"(?:boards|job-boards)\.greenhouse\.io$",
        r"/jobs/\d+",
    ),
    AtsCareerPattern(
        "lever",
        r"jobs\.lever\.co/([^/?#]+)",
        "jobs.lever.co/{0}",
        "https://api.lever.co/v0/postings/{slug}?mode=json",
        "site:jobs.lever.co",
        r"^jobs\.lever\.co$",
        r"^/[^/]+/[0-9a-f-]{36}",
    ),
    AtsCareerPattern("bamboohr", r"([^/.]+)\.bamboohr\.com", "{0}.bamboohr.com"),
    AtsCareerPattern(
        "smartrecruiters",
        r"jobs\.smartrecruiters\.com/([^/?#]+)",
        "jobs.smartrecruiters.com/{0}",
        "https://api.smartrecruiters.com/v1/companies/{slug}/postings?status=PUBLISHED",
        "site:jobs.smartrecruiters.com",
        r"^jobs\.smartrecruiters\.com$",
        r"^/[^/]+/\d+",
    ),
    AtsCareerPattern(
        "workable",
        r"apply\.workable\.com/([^/?#]+)",
        "apply.workable.com/{0}",
        "https://apply.workable.com/api/v3/accounts/{slug}/jobs?details=true&status=published",
        "site:apply.workable.com",
        r"^apply\.workable\.com$",
        r"^/[^/]+/j/[A-F0-9]+",
    ),
    AtsCareerPattern(
        "ashby",
        r"jobs\.ashbyhq\.com/([^/?#]+)",
        "jobs.ashbyhq.com/{0}",
        "https://api.ashbyhq.com/posting-api/job-board/{slug}",
        "site:jobs.ashbyhq.com",
        r"^jobs\.ashbyhq\.com$",
        r"^/[^/]+/[0-9a-f-]{36}",
    ),
    AtsCareerPattern(
        "hibob",
        r"([^/.]+)\.careers\.hibob\.com",
        "{0}.careers.hibob.com",
        "",
        "site:careers.hibob.com/jobs",
        r"\.careers\.hibob\.com$",
        r"/jobs/[0-9a-f-]{36}",
    ),
    AtsCareerPattern(
        "personio",
        r"([^/.]+)\.jobs\.personio\.de",
        "{0}.jobs.personio.de",
        # Personio's newer /api/v1/jobs JSON endpoint sits behind a Vercel bot
        # checkpoint on many tenants; the public XML feed is the stable one.
        "https://{slug}.jobs.personio.de/xml",
        "site:jobs.personio.de OR site:jobs.personio.com",
        r"(?:jobs\.personio\.(?:de|com)|\.jobs\.personio\.de)$",
        r"/job/",
    ),
    AtsCareerPattern(
        "breezy",
        r"([^/.]+)\.breezy\.hr",
        "{0}.breezy.hr",
        "https://{slug}.breezy.hr/json",
        "site:breezy.hr/p",
        r"\.breezy\.hr$",
        r"/p/",
    ),
    AtsCareerPattern(
        "recruitee",
        r"([^/.]+)\.recruitee\.com",
        "{0}.recruitee.com",
        "https://{slug}.recruitee.com/api/offers",
        "site:recruitee.com",
        r"recruitee\.com$",
        r"/o/",
    ),
    AtsCareerPattern(
        "teamtailor",
        r"([^/.]+)\.teamtailor\.com",
        "{0}.teamtailor.com",
        "https://{slug}.teamtailor.com/jobs.json",
        "site:teamtailor.com/jobs",
        r"\.teamtailor\.com$",
        r"/jobs/",
    ),
    AtsCareerPattern(
        "workday",
        r"([^/]+\.myworkdayjobs\.com/[^/?#]+)",
        "{0}",
        "",
        "site:myworkdayjobs.com",
        r"myworkdayjobs\.com$",
        r"/job/",
    ),
)

_DIRECT_ATS_NAMES = {
    "greenhouse",
    "lever",
    "smartrecruiters",
    "workable",
    "ashby",
    "hibob",
    "personio",
    "breezy",
    "recruitee",
    "teamtailor",
    "workday",
    "bamboohr",
}


def _without_scheme(url: str) -> str:
    return re.sub(r"^https?://", "", url.strip()).rstrip("/")


def ats_endpoint_patterns() -> list[tuple[re.Pattern, str, str]]:
    return [(re.compile(ats.pattern, re.IGNORECASE), ats.name, ats.api_template) for ats in ATS_CAREER_PATTERNS]


def ats_discovery_sites() -> dict[str, tuple[str, str, str]]:
    return {
        ats.name: (
            ats.discovery_site_query,
            ats.discovery_host_pattern,
            ats.discovery_path_pattern,
        )
        for ats in ATS_CAREER_PATTERNS
        if ats.discovery_site_query
    }


def ats_search_sites() -> tuple[str, ...]:
    sites: list[str] = []
    for site_query, _, _ in ats_discovery_sites().values():
        sites.extend(part.strip(" ()") for part in site_query.split(" OR ") if part.strip(" ()"))
    return tuple(dict.fromkeys(sites))


def detect_ats(career_url: str) -> tuple[str, str] | None:
    """Return (ats_name, slug) for supported direct ATS career URLs."""
    normalized = _without_scheme(career_url)
    for ats in ATS_CAREER_PATTERNS:
        if ats.name not in _DIRECT_ATS_NAMES:
            continue
        match = re.search(ats.pattern, normalized, re.IGNORECASE)
        if match:
            return ats.name, match.group(1)
    return None


def extract_career_url(job_url: str) -> str | None:
    """Derive the ATS base/career URL from a specific job posting URL."""
    normalized = _without_scheme(job_url)
    for ats in ATS_CAREER_PATTERNS:
        match = re.search(ats.pattern, normalized, re.IGNORECASE)
        if match:
            return ats.career_template.format(match.group(1))
    return None


def company_slug_from_url(url: str) -> str | None:
    """Return the most likely company slug embedded in an ATS or career URL."""
    normalized = _without_scheme(url)
    for ats in ATS_CAREER_PATTERNS:
        match = re.search(ats.pattern, normalized, re.IGNORECASE)
        if match:
            if ats.name == "workday":
                return match.group(1).split(".", 1)[0]
            return match.group(1)

    parsed = urlparse(f"https://{normalized}")
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.startswith(("careers.", "jobs.")) and len(parsed.netloc.split(".")) > 2:
        return parsed.netloc.split(".")[1]
    if parts and re.search(r"\b(careers?|jobs?)\b", parsed.netloc, re.IGNORECASE):
        return parts[0]
    return None


def company_name_from_url(url: str) -> str | None:
    slug = company_slug_from_url(url)
    if not slug:
        return None
    return slug.replace("-", " ").replace("_", " ").strip().title()
