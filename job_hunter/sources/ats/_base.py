from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable

from job_hunter.core.config import get_timeout, load_api_config
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources._base import JobSourceAdapter

_TIMEOUT = get_timeout("ats_scraper")
_ATS_CFG = load_api_config().get("http", {}).get("ats_scraper", {}) or {}
_SNIPPET_CHARS = int(_ATS_CFG.get("snippet_chars", 2000))


def _build_snippet(location: str, body: str) -> str:
    body = body[:_SNIPPET_CHARS]
    return f"{location} - {body}" if location else body


class AtsJobSourceAdapter(JobSourceAdapter):
    def __init__(
        self,
        slug: str,
        company_name: str,
        excluded_title_terms: list[str] | None = None,
    ) -> None:
        self.slug = slug
        self.company_name = company_name
        self.excluded_title_terms = excluded_title_terms

    @abstractmethod
    def _fetch_ats_jobs(
        self,
        slug: str,
        company_name: str,
        location_filter: str,
        title_filters: list[str],
        excluded_title_terms: list[str] | None = None,
    ) -> list[dict]:
        raise NotImplementedError

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        excluded = self.excluded_title_terms
        if excluded is None:
            excluded = params.excluded_title_terms
        return [
            JobPosting.from_dict(job)
            for job in self._fetch_ats_jobs(
                self.slug,
                self.company_name,
                params.location,
                params.job_titles,
                excluded,
            )
        ]


def make_ats_source(name: str, fetch_fn: Callable) -> type[AtsJobSourceAdapter]:
    """Create an AtsJobSourceAdapter subclass that delegates to fetch_fn."""

    def _fetch_ats_jobs(self, *args, **kwargs) -> list[dict]:
        return fetch_fn(*args, **kwargs)

    return type(
        f"{name.title()}Source",
        (AtsJobSourceAdapter,),
        {"source_name": property(lambda self, n=name: n), "_fetch_ats_jobs": _fetch_ats_jobs},
    )
