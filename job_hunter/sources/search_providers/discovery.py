"""Company homepage and career URL discovery helpers."""

from __future__ import annotations

from urllib.parse import urlparse

from job_hunter.sources.ats_urls import ats_search_sites
from job_hunter.sources.search_providers._url_utils import canonicalize_url
from job_hunter.sources.search_providers.router import SearchRouter, search_web


def discover_company_homepage(company_name: str, region_config: dict) -> str | None:
    location = region_config.get("location", "")
    query = f'"{company_name}" "{location}" official website careers'
    results = SearchRouter().search(query, region_config, count=5)
    for result in results:
        parsed = urlparse(result.url)
        if parsed.netloc and "linkedin." not in parsed.netloc and "glassdoor." not in parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return None


def search_career_urls(company_name: str, region_config: dict, count: int = 7) -> list[dict]:
    location = region_config.get("location", "")
    job_titles = region_config.get("job_titles", [])
    title_query = " OR ".join(f'"{title}"' for title in job_titles)
    ats_sites = ats_search_sites()
    queries = [f'"{company_name}" "{location}" {site}' for site in ats_sites]
    if title_query:
        queries.append(f'"{company_name}" {location} {title_query} careers jobs')
    queries.append(f'"{company_name}" "{location}" careers jobs')
    out: list[dict] = []
    seen: set[str] = set()
    for query in queries:
        for item in search_web(query, region_config, count=count):
            canonical = canonicalize_url(item["url"])
            if canonical in seen:
                continue
            seen.add(canonical)
            out.append(item)
    return out
