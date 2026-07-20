"""Sitemap and common career-path discovery."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import defusedxml.ElementTree as ET
import requests

from job_hunter.config.loader import get_timeout
from job_hunter.core.utils import title_matches
from job_hunter.sources.career_pages._ats_patterns import _CAREER_PATHS
from job_hunter.sources.search import USER_AGENT, canonicalize_url

logger = logging.getLogger(__name__)


def _local_tag(tag: str) -> str:
    """Strip the XML namespace off an ElementTree tag, e.g. '{...}loc' -> 'loc'."""
    return tag.rsplit("}", 1)[-1]


def _parse_sitemap_locs(xml_bytes: bytes) -> list[str]:
    """Extract <loc> URLs from sitemap XML using defusedxml — never BeautifulSoup,
    which needs lxml (not a dependency here) for a real XML parser and otherwise
    either fails or warns under html.parser; and never bare xml.etree, which is
    vulnerable to entity-expansion attacks on a remote, user-configured URL. A
    sitemap index's nested <sitemap><loc> entries point at other sitemaps, not
    jobs, so they're skipped rather than recursed into (no unbounded crawling)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        logger.debug("[sitemap] malformed XML: %s", exc)
        return []
    if _local_tag(root.tag) == "sitemapindex":
        return []
    return [
        loc.text.strip()
        for entry in root
        for loc in entry
        if _local_tag(loc.tag) == "loc" and loc.text and loc.text.strip()
    ]


def _probe_sitemap(base_url: str, timeout: int) -> list[str]:
    """Return job-detail URLs found in /sitemap.xml."""
    sitemap_url = base_url.rstrip("/") + "/sitemap.xml"
    try:
        resp = requests.get(
            sitemap_url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            allow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as e:
        logger.debug("[sitemap] failed to fetch %s: %s", sitemap_url, e)
        return []
    return _parse_sitemap_locs(resp.content)


def _probe_career_paths(base_url: str, timeout: int) -> list[str]:
    """Return URLs that responded successfully from common career-page paths."""
    found = []
    for path in _CAREER_PATHS:
        url = base_url.rstrip("/") + path
        try:
            resp = requests.head(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
                allow_redirects=True,
            )
            if resp.ok:
                found.append(resp.url or url)
        except Exception as e:
            logger.debug("[sitemap] probe failed for %s: %s", url, e)
    return found


def discover_via_sitemap(
    career_url: str,
    company_name: str,
    title_filters: list[str],
) -> list[dict]:
    """Return job-detail URLs discovered through sitemap or common career paths."""
    parsed = urlparse(career_url if "://" in career_url else f"https://{career_url}")
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    timeout = get_timeout("ats_scraper")

    candidate_urls: list[str] = []

    sitemap_locs = _probe_sitemap(base_url, timeout)
    job_hint_locs = [
        loc for loc in sitemap_locs if any(hint in loc.lower() for hint in ("/job", "/career", "/position", "/opening"))
    ]
    candidate_urls.extend(job_hint_locs)

    if not candidate_urls:
        candidate_urls.extend(_probe_career_paths(base_url, timeout))

    jobs: list[dict] = []
    seen: set[str] = set()

    for url in candidate_urls:
        canonical = canonicalize_url(url)
        if canonical in seen:
            continue
        seen.add(canonical)
        if not title_matches(url, title_filters):
            continue
        jobs.append(
            {
                "title": "",
                "company": company_name,
                "url": url,
                "location": "",
                "posted_date_text": "",
                "snippet": "",
                "source": "career_page:sitemap",
                "extraction_method": "sitemap",
            }
        )

    return jobs
