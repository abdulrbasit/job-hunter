"""ATS slug cache: harvest company slugs from job URLs, persist, and query ATS APIs directly.

Self-seeding: every pipeline run extracts slugs from discovered ATS URLs and writes them to
outputs/state/ats_slugs.yml. Subsequent runs query each platform's public job-list API for
all cached slugs — no search engine API keys required.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from job_hunter.catalog.loader import load_companies
from job_hunter.constants import ATS_DISCOVERY_API_TIMEOUT
from job_hunter.core.utils import location_matches, title_matches
from job_hunter.models import JobPosting
from job_hunter.sources.ats_urls import detect_ats

logger = logging.getLogger(__name__)

_SLUG_STORE_RELPATH = Path("outputs/state/ats_slugs.yml")


def harvest_slugs(jobs: list[JobPosting | dict]) -> dict[str, set[str]]:
    """Extract {platform: {slug}} from any collection of job records."""
    result: dict[str, set[str]] = {}
    for job in jobs:
        url = job.url if isinstance(job, JobPosting) else job.get("url", "")
        if not url:
            continue
        detected = detect_ats(url)
        if detected:
            platform, slug = detected
            result.setdefault(platform, set()).add(slug.lower())
    return result


def catalog_slugs(config: dict) -> dict[str, set[str]]:
    """ATS slugs from the bundled company catalog, filtered to the user's enabled
    regions and industry exclusions; platforms with a public list API only."""
    from job_hunter.catalog.merge import _enabled_country_codes, _excluded_industry_ids
    from job_hunter.sources.ats_apis import _FETCHERS

    enabled_countries = _enabled_country_codes(config)
    excluded = _excluded_industry_ids((config.get("exclusions", {}) or {}).get("industries", []) or [])
    result: dict[str, set[str]] = {}
    for company in load_companies():
        if excluded and set(company.industry_ids) & excluded:
            continue
        if (
            enabled_countries
            and not (set(company.country_codes) | set(company.remote_country_codes)) & enabled_countries
        ):
            continue
        detected = detect_ats(company.career_url)
        if detected and detected[0] in _FETCHERS:
            result.setdefault(detected[0], set()).add(detected[1].lower())
    return result


def load_slug_store(workspace: Path) -> dict[str, list[str]]:
    """Load ats_slugs.yml; return empty dict if missing or malformed."""
    path = workspace / _SLUG_STORE_RELPATH
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return {k: list(v) for k, v in data.items() if isinstance(v, list)}
    except Exception as exc:
        logger.warning("[ats_slugs] Failed to load slug store: %s", exc)
        return {}


def update_slug_store(workspace: Path, new_slugs: dict[str, set[str]]) -> None:
    """Merge new slugs into the store and write back (deduplicates, sorts)."""
    if not new_slugs:
        return
    store = load_slug_store(workspace)
    for platform, slugs in new_slugs.items():
        existing = set(store.get(platform, []))
        store[platform] = sorted(existing | slugs)
    path = workspace / _SLUG_STORE_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(store, default_flow_style=False, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )
    total = sum(len(v) for v in store.values())
    logger.info("[ats_slugs] Slug store updated: %d slugs across %d platforms", total, len(store))


def query_ats_by_slugs(
    slug_store: dict[str, list[str]],
    title_filters: list[str],
    regions: dict,
    excluded_title_terms: list[str],
) -> list[dict]:
    """Query each cached slug against its platform's public job-list API.

    Returns job dicts compatible with JobPosting.model_validate(). Location
    filtering is advisory — jobs with no location pass through so the policy
    stage can decide.
    """
    from job_hunter.sources.ats_apis import fetch_platform_jobs

    if not slug_store:
        return []

    locations = [config.get("location", "") for config in regions.values() if config.get("location")]
    region_key = next(iter(regions), "")
    results: list[dict] = []
    seen: set[str] = set()

    pairs = [(platform, slug) for platform, slugs in slug_store.items() for slug in slugs]
    if not pairs:
        return []
    with ThreadPoolExecutor(max_workers=min(16, len(pairs))) as pool:
        fetched = list(pool.map(lambda p: fetch_platform_jobs(p[0], p[1], ATS_DISCOVERY_API_TIMEOUT), pairs))

    for (platform, slug), jobs in zip(pairs, fetched, strict=True):
        company = slug.replace("-", " ").replace("_", " ").title()
        for j in jobs:
            title = j.get("title", "")
            url = j.get("url", "")
            if not title or not url or url in seen:
                continue
            if not title_matches(title, title_filters, excluded_title_terms):
                continue
            loc = j.get("location", "")
            if loc and locations and not any(location_matches(loc, lf) for lf in locations):
                continue
            seen.add(url)
            results.append(
                {
                    "title": title,
                    "company": company,
                    "url": url,
                    "location": loc,
                    "snippet": j.get("snippet", ""),
                    "source": f"ats_slug/{platform}",
                    "region": region_key,
                    "posted_date_text": "",
                    "search_query": f"{title} @ {region_key}",
                }
            )

    logger.info("[ats_slugs] Direct ATS query returned %d jobs", len(results))
    return results
