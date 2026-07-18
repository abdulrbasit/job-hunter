"""Public JobTeaser student and graduate listings."""

from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_hunter.core.posting_types import detect_posting_signals
from job_hunter.core.utils import title_is_allowed
from job_hunter.models import JobPosting, SearchParams
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.source_config import job_board_enabled, job_board_timeout

_BASE_URL = "https://www.jobteaser.com"
_SUPPORTED = frozenset(
    {"AT", "BE", "CH", "DE", "DK", "ES", "FI", "FR", "GB", "IE", "IT", "LU", "NL", "NO", "PL", "PT", "SE"}
)


class JobTeaserSource(JobSourceAdapter):
    supported_countries = _SUPPORTED

    @property
    def source_name(self) -> str:
        return "jobteaser"

    def is_enabled(self, api_config: dict) -> bool:
        boards = api_config.get("http", {}).get("job_boards", {})
        return bool(boards.get(self.source_name, {}).get("enabled", True))

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        if not self.supports_country(params.country) or not job_board_enabled(self.source_name):
            return []
        locale = params.search_lang if params.search_lang in {"de", "en", "es", "fr", "it", "nl"} else "en"
        response = requests.get(
            f"{_BASE_URL}/{locale}/job-offers",
            params={"locale": params.country.lower()},
            timeout=job_board_timeout(self.source_name),
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        jobs: list[JobPosting] = []
        for card in soup.find_all("article"):
            link = card.find("a", href=True)
            heading = card.find(["h2", "h3"])
            if not link or not heading:
                continue
            title = heading.get_text(" ", strip=True)
            if not title_is_allowed(
                title,
                params.job_titles,
                params.excluded_title_terms,
                relaxed_student=params.student_mode,
            ):
                continue
            text_parts = [node.get_text(" ", strip=True) for node in card.find_all(["p", "span"])]
            company = text_parts[0] if text_parts else ""
            location = next((value for value in text_parts if params.location.casefold() in value.casefold()), "")
            signals = detect_posting_signals(title, " ".join(text_parts))
            jobs.append(
                JobPosting(
                    title=title,
                    company=company,
                    url=urljoin(_BASE_URL, str(link["href"])),
                    location=location,
                    snippet=" ".join(text_parts)[:3000],
                    source="JobTeaser",
                    search_query=f"student feed @ {params.region_key}",
                    region=params.region_key,
                    posting_type=signals.posting_type,
                )
            )
        return jobs
