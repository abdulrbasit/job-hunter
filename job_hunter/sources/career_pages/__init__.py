"""Deterministic career-page extraction ladder.

Extraction order (cheapest and most structured first):

1. Known ATS/public endpoint detection: if the URL matches a supported ATS
   platform, fetch jobs from the public JSON API directly.
2. Embedded JobPosting JSON-LD extraction: parse structured data from the
   page HTML without rendering JavaScript.
3. Sitemap / common career-path discovery: probe /sitemap.xml and
   well-known career paths for job-detail URLs.
4. Static HTML extraction: parse anchor links from the raw HTML response.
5. Playwright rendering: only when static extraction yields nothing.

Each rung records ``extraction_method`` in the returned job dict so callers
can tell how a candidate was found without inspecting the URL.

No search provider, LLM, or Kestrel code is used or imported here.
"""

from __future__ import annotations

import logging

import requests  # noqa: F401 — exposed so tests can patch career_pages.requests.get/head

from job_hunter.sources.career_pages._ats_patterns import (
    _ATS_URL_PATTERNS,
    _CAREER_PATHS,
    _fetch_ats_endpoint_jobs,
    _normalise_ats_job,
    detect_ats,
    detect_ats_from_url,
)
from job_hunter.sources.career_pages._jsonld import extract_jsonld_jobs
from job_hunter.sources.career_pages._ladder import (
    _fetch_html_safe,
    _try_playwright,
    _try_sitemap_discovery,
    _try_static_html,
)
from job_hunter.sources.career_pages._rendering import (
    extract_from_firecrawl,
    extract_from_lightpanda,
    extract_from_rendered_html,
    extract_from_static_html,
)
from job_hunter.sources.career_pages._sitemap import (
    _probe_career_paths,
    _probe_sitemap,
    discover_via_sitemap,
)
from job_hunter.sources.search.fetchers import (
    fetch_firecrawl_career_jobs,
    fetch_lightpanda_career_jobs,
    fetch_playwright_career_jobs,
)

logger = logging.getLogger(__name__)


def extract_career_page_jobs(
    company: dict,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Run the full extraction ladder for a company career URL.

    Returns jobs with ``extraction_method`` set to the rung that produced them:
    ``ats_api``, ``jsonld``, ``sitemap``, ``static_html``, ``lightpanda``,
    ``playwright``, or ``firecrawl``.

    Defined here (not in _ladder) so that monkeypatching the module-level names
    in this package's namespace affects the function's lookups at call time.
    """
    import sys

    _pkg = sys.modules[__name__]

    career_url = company.get("career_url", "")
    name = company.get("name", "")
    location = company.get("location", "")

    if not career_url:
        return []

    # Rung 1: ATS public endpoint
    ats_result = _pkg.detect_ats_from_url(career_url)
    if ats_result:
        ats_name, slug = ats_result
        _, _, api_template = _pkg.detect_ats(career_url)
        if api_template:
            jobs = _pkg._fetch_ats_endpoint_jobs(slug, ats_name, api_template, title_filters, excluded_title_terms)
            if jobs:
                logger.debug(
                    "[career_pages] rung=ats_api company=%s ats=%s jobs=%d",
                    name,
                    ats_name,
                    len(jobs),
                )
                return jobs

    # Rung 2: JSON-LD on the career page HTML
    url = career_url if "://" in career_url else f"https://{career_url}"
    html_content, _ = _pkg._fetch_html_safe(url)
    html_base_url = url

    if html_content:
        jsonld_jobs = _pkg.extract_jsonld_jobs(html_content, html_base_url, name, title_filters)
        if jsonld_jobs:
            logger.debug("[career_pages] rung=jsonld company=%s jobs=%d", name, len(jsonld_jobs))
            return jsonld_jobs

    # Rung 3: Sitemap / common career-path discovery
    sitemap_jobs = _pkg._try_sitemap_discovery(career_url, name, title_filters, excluded_title_terms)
    if sitemap_jobs:
        logger.debug("[career_pages] rung=sitemap company=%s jobs=%d", name, len(sitemap_jobs))
        return sitemap_jobs

    # Rung 4: Static HTML extraction
    if html_content:
        raw_jobs = _pkg._try_static_html(
            html_content, html_base_url, name, title_filters, location, excluded_title_terms
        )
        if raw_jobs:
            logger.debug("[career_pages] rung=static_html company=%s jobs=%d", name, len(raw_jobs))
            return raw_jobs

    # Rung 5: Lightpanda read-only rendering
    lightpanda_jobs = _pkg.fetch_lightpanda_career_jobs(company, title_filters, excluded_title_terms)
    for job in lightpanda_jobs:
        job.setdefault("extraction_method", "lightpanda")
    if lightpanda_jobs:
        logger.debug("[career_pages] rung=lightpanda company=%s jobs=%d", name, len(lightpanda_jobs))
        return lightpanda_jobs

    # Rung 6: Playwright rendering
    pw_jobs = _pkg._try_playwright(career_url, name, title_filters, location, excluded_title_terms)
    if pw_jobs:
        logger.debug("[career_pages] rung=playwright company=%s jobs=%d", name, len(pw_jobs))
        return pw_jobs

    # Rung 7: Firecrawl cloud markdown
    firecrawl_jobs = _pkg.fetch_firecrawl_career_jobs(company, title_filters, excluded_title_terms)
    for job in firecrawl_jobs:
        job.setdefault("extraction_method", "firecrawl")
    if firecrawl_jobs:
        logger.debug("[career_pages] rung=firecrawl company=%s jobs=%d", name, len(firecrawl_jobs))
    return firecrawl_jobs


__all__ = [
    "detect_ats",
    "detect_ats_from_url",
    "extract_jsonld_jobs",
    "discover_via_sitemap",
    "extract_from_static_html",
    "extract_from_rendered_html",
    "extract_from_lightpanda",
    "extract_from_firecrawl",
    "extract_career_page_jobs",
    "_fetch_html_safe",
    "_try_playwright",
    "_try_sitemap_discovery",
    "_try_static_html",
    "fetch_firecrawl_career_jobs",
    "fetch_lightpanda_career_jobs",
    "fetch_playwright_career_jobs",
    "_ATS_URL_PATTERNS",
    "_CAREER_PATHS",
    "_normalise_ats_job",
    "_fetch_ats_endpoint_jobs",
    "_probe_sitemap",
    "_probe_career_paths",
]
