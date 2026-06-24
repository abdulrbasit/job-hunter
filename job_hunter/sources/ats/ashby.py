from __future__ import annotations

import logging

import requests

from job_hunter.core.utils import location_matches, strip_html, title_matches
from job_hunter.sources.ats._base import _TIMEOUT, _build_snippet

logger = logging.getLogger(__name__)

_GQL_URL = "https://jobs.ashbyhq.com/api/non-user-graphql"

# jobBoardWithTeams returns brief listing: {id, title, locationName} only.
_Q_LIST = """
query($slug: String!) {
  board: jobBoardWithTeams(organizationHostedJobsPageName: $slug) {
    jobPostings { id title locationName }
  }
}
"""

# Per-job detail: fetch description for matched postings only.
_Q_DETAIL = """
query($slug: String!, $id: String!) {
  jobPosting(organizationHostedJobsPageName: $slug, jobPostingId: $id) {
    descriptionHtml
  }
}
"""


def _gql(query: str, variables: dict) -> dict:
    resp = requests.post(
        _GQL_URL,
        json={"query": query, "variables": variables},
        headers={"Content-Type": "application/json"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errors"):
        raise ValueError(data["errors"][0]["message"])
    return data.get("data") or {}


def fetch_ashby_jobs(
    slug: str,
    company_name: str,
    location_filter: str,
    title_filters: list[str],
    excluded_title_terms: list[str] | None = None,
) -> list[dict]:
    """Fetch jobs from Ashby GraphQL API (no auth required)."""
    try:
        board = _gql(_Q_LIST, {"slug": slug}).get("board") or {}
        postings = board.get("jobPostings") or []
    except Exception as e:
        logger.warning("[ashby] %s: %s", slug, e)
        return []

    jobs = []
    for posting in postings:
        title = posting.get("title", "")
        location = posting.get("locationName", "")

        if not location_matches(location, location_filter):
            logger.debug("[ashby] skip wrong location: %s (%s)", title, location)
            continue
        if not title_matches(title, title_filters, excluded_title_terms):
            continue

        job_id = posting.get("id", "")
        description = ""
        try:
            detail = _gql(_Q_DETAIL, {"slug": slug, "id": job_id})
            description = strip_html((detail.get("jobPosting") or {}).get("descriptionHtml", ""))
        except Exception as e:
            logger.debug("[ashby] detail fetch failed for %s: %s", job_id, e)

        jobs.append(
            {
                "title": title,
                "company": company_name,
                "url": f"https://jobs.ashbyhq.com/{slug}/{job_id}",
                "posted": "",
                "location": location,
                "snippet": _build_snippet(location, description),
                "source": "Ashby API",
            }
        )

    logger.info("[ashby] %s: %d matching jobs", slug, len(jobs))
    return jobs
