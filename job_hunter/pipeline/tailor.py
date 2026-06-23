"""Tailor-mode pipeline: fetch JDs from links or raw text, then dispatch."""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING, Any

from job_hunter.core.config import get_config
from job_hunter.core.utils import title_matches
from job_hunter.sources.jd_fetcher import fetch_jd, jd_from_text
from job_hunter.tracking.tracker import load_processed

if TYPE_CHECKING:
    from job_hunter.core.url_liveness import UrlLivenessCache

logger = logging.getLogger(__name__)


def _parse_urls(raw: str) -> list[str]:
    """Split a comma- or newline-separated string of URLs into a clean list."""
    return [
        token.strip()
        for token in raw.replace(",", "\n").splitlines()
        if token.strip() and not token.strip().startswith("#")
    ]


def _load_search_rules() -> tuple[list[str], list[str]]:
    """Return configured accepted job titles and excluded title terms."""
    data = get_config("job_hunter")
    title_filters = data.get("job_titles", [])
    excluded_title_terms = (data.get("exclusions", {}) or {}).get("title_terms", [])
    return title_filters, excluded_title_terms


def _jobs_from_links(
    raw: str,
    force: bool,
    existing_urls: set[str],
) -> list[dict[str, Any]]:
    """
    Fetch job descriptions from a list of direct URLs.

    Skips URLs already in outputs/state/discovered_urls.yml unless --force is set.
    """
    jobs: list[dict[str, Any]] = []
    title_filters, excluded_title_terms = _load_search_rules()
    for url in _parse_urls(raw):
        if not force and url in existing_urls:
            logger.info("  [skip] Already processed (use --force to re-tailor): %s", url)
            continue
        job = fetch_jd(url)
        if job:
            if not title_matches(job.get("title", ""), title_filters, excluded_title_terms):
                logger.info(
                    "  [skip] Irrelevant title after JD extraction: %s @ %s",
                    job.get("title", "?"),
                    job.get("company", "?"),
                )
                continue
            jobs.append(job)
            logger.info("  fetched: %s @ %s", job["title"], job["company"])
        else:
            logger.warning("  could not fetch JD: %s", url)
    return jobs


def _jobs_from_raw_text(
    text: str,
    title: str | None,
    company: str | None,
    force: bool,
    existing_urls: set[str],
) -> list[dict[str, Any]]:
    """Build a single job dict from raw pasted JD text."""
    job = jd_from_text(text, title=title, company=company)
    if not job:
        logger.error("[pipeline] Could not parse job from raw text.")
        return []
    if not force and job["url"] in existing_urls:
        logger.info("  [skip] Already processed (use --force to re-tailor): %s", job["url"])
        return []
    logger.info("  raw input: %s @ %s", job["title"], job["company"])
    return [job]


def run_tailor(
    args: dict,
    api_cfg: dict[str, Any],
    scoring_cfg: dict[str, Any],
    url_liveness: UrlLivenessCache,
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """
    Execute tailor-links or tailor-raw mode: fetch/parse JDs.

    Pre-condition: caller has already validated that the required args
    (``--links``/``TAILOR_LINKS`` for tailor-links, ``--jd`` for tailor-raw)
    are present and has handled the missing-arg exit code (1).

    Returns (jobs, existing_urls, existing_titles) ready for downstream processing,
    or ([], existing_urls, existing_titles) when no jobs could be fetched/parsed.
    """
    existing_urls = load_processed()
    existing_titles = set()

    if args["mode"] == "tailor-links":
        raw_links = args["links"] or os.environ.get("TAILOR_LINKS", "")
        logger.info("[pipeline] Step 1: Fetching job descriptions from links...")
        jobs = _jobs_from_links(raw_links, args["force"], existing_urls)

    else:  # tailor-raw
        raw_jd = args["jd"]
        if raw_jd == "-":
            raw_jd = sys.stdin.read()
        logger.info("[pipeline] Step 1: Parsing raw job description...")
        jobs = _jobs_from_raw_text(raw_jd, args["title"], args["company"], args["force"], existing_urls)

    return jobs, existing_urls, existing_titles
