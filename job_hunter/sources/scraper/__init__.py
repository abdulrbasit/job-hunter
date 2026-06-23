"""Hybrid job scraper package."""

from __future__ import annotations

from job_hunter.sources.scraper._boards import collect_board_sources, scrape
from job_hunter.sources.scraper._companies import _url_matches_career_site
from job_hunter.sources.scraper._discovery import (
    brave_search,
    collect_ai_web_search,
    collect_ats_discovery,
)
from job_hunter.sources.scraper._stats import ScrapeStats, SourceStats

__all__ = [
    "ScrapeStats",
    "SourceStats",
    "_url_matches_career_site",
    "brave_search",
    "collect_ai_web_search",
    "collect_ats_discovery",
    "collect_board_sources",
    "scrape",
]
