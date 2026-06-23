"""JSON-LD JobPosting extraction from page HTML."""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

from job_hunter.constants import CAREER_PAGE_SNIPPET_CHARS
from job_hunter.sources.search_providers import canonicalize_url


def extract_jsonld_jobs(
    html: str,
    base_url: str,
    company_name: str,
    title_filters: list[str] | None = None,
) -> list[dict]:
    """Parse embedded JobPosting JSON-LD blocks from page HTML.

    Follows the schema.org JobPosting type as documented at
    https://schema.org/JobPosting and Google's job posting structured data
    guidance at https://developers.google.com/search/docs/appearance/structured-data/job-posting.
    """
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[dict] = []
    seen: set[str] = set()

    for script_tag in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            payload = json.loads(script_tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        # May be a single object or a list; flatten @graph wrappers before iterating
        # so that inner items are not missed when the for-loop iterator is already bound.
        raw_items = payload if isinstance(payload, list) else [payload]
        items: list = []
        for raw in raw_items:
            if isinstance(raw, dict) and "@graph" in raw:
                inner = raw["@graph"]
                if isinstance(inner, list):
                    items.extend(d for d in inner if isinstance(d, dict))
            elif isinstance(raw, dict):
                items.append(raw)

        for item in items:
            type_val = item.get("@type", "")
            if type_val != "JobPosting" and "JobPosting" not in (
                type_val if isinstance(type_val, list) else [type_val]
            ):
                continue

            title = str(item.get("title") or item.get("name") or "").strip()
            if not title:
                continue

            if title_filters:
                from job_hunter.core.utils import title_matches

                if not title_matches(title, title_filters):
                    continue

            apply_url = ""
            apply_info = item.get("apply") or item.get("applyUrl") or {}
            if isinstance(apply_info, dict):
                apply_url = str(apply_info.get("url") or "").strip()
            elif isinstance(apply_info, str):
                apply_url = apply_info.strip()

            job_url = apply_url or base_url
            canonical = canonicalize_url(job_url)
            if canonical in seen:
                continue
            seen.add(canonical)

            location_raw = item.get("jobLocation") or {}
            if isinstance(location_raw, dict):
                address = location_raw.get("address") or {}
                if isinstance(address, dict):
                    location = (
                        address.get("addressLocality")
                        or address.get("addressRegion")
                        or address.get("addressCountry")
                        or ""
                    )
                else:
                    location = str(address)
            elif isinstance(location_raw, str):
                location = location_raw
            else:
                location = ""

            employer_raw = item.get("hiringOrganization") or {}
            if isinstance(employer_raw, dict):
                employer = str(employer_raw.get("name") or company_name).strip()
            else:
                employer = company_name

            description_raw = item.get("description") or ""
            snippet = str(description_raw)[:CAREER_PAGE_SNIPPET_CHARS].strip()

            jobs.append(
                {
                    "title": title,
                    "company": employer,
                    "url": job_url,
                    "location": str(location).strip(),
                    "posted": str(item.get("datePosted") or "").strip(),
                    "snippet": snippet,
                    "source": "career_page:jsonld",
                    "extraction_method": "jsonld",
                    "raw_schema_org": item,
                }
            )

    return jobs
