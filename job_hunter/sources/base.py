"""JobSourceAdapter — abstract contract for every job source.

Rules (per dev-source skill):
  - fetch() must NEVER raise. Return [] on any error and log at WARNING.
  - All returned JobPosting objects must have url, title, company, source set.
  - Input is always SearchParams; output is always list[JobPosting].
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from job_hunter.models import JobPosting, SearchParams

logger = logging.getLogger(__name__)


class JobSourceAdapter(ABC):
    """Base class for every job source. One source, one responsibility.

    Tier controls which sources run per --depth level:
      "free"   — no API key required (Himalayas, Remotive, etc.)
      "api"    — keyed API (Adzuna, Reed, Jooble, RapidAPI/JSearch)
      "search" — paid web-search providers (Brave, Tavily, Exa, ATS discovery)
      "browser"— Playwright rendering (career pages, JS-gated sites)
    """

    tier: str = "free"  # override per adapter; used by --depth filtering
    global_feed: bool = False

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique identifier used in JobPosting.source and log messages."""

    def is_enabled(self, api_config: dict) -> bool:
        """Return True by default; sources may override to check config flags."""
        return True

    @abstractmethod
    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        """Implementation. May raise — caller wraps in try/except."""

    def fetch(self, params: SearchParams) -> list[JobPosting]:
        """Public entry point. Never raises; returns [] on failure."""
        try:
            results = self._fetch(params)
            logger.info("[%s] fetched %d jobs", self.source_name, len(results))
            return results
        except Exception as exc:
            logger.warning("[%s] fetch failed: %s", self.source_name, exc)
            return []
