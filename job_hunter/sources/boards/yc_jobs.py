"""Bounded public Y Combinator jobs adapter."""

from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from job_hunter.core.utils import title_is_allowed
from job_hunter.models import CompanyType, JobPosting, SearchParams
from job_hunter.sources.base import JobSourceAdapter
from job_hunter.sources.source_config import job_board_enabled, job_board_timeout

_URL = "https://www.ycombinator.com/jobs"


class YCJobsSource(JobSourceAdapter):
    startup_source = True

    @property
    def source_name(self) -> str:
        return "yc_jobs"

    def _fetch(self, params: SearchParams) -> list[JobPosting]:
        if not job_board_enabled(self.source_name):
            return []
        response = requests.get(_URL, timeout=job_board_timeout(self.source_name))
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        jobs: list[JobPosting] = []
        cards = soup.find_all("article")
        if not cards:
            cards = [
                link
                for link in soup.find_all("a", href=True)
                if "/companies/" in str(link["href"]) and "/jobs/" in str(link["href"])
            ]
        for card in cards[: params.max_results]:
            if card.name == "a":
                link = card
                heading = card
                container = card.find_parent(["li", "div"]) or card.parent
            else:
                link = card.find("a", href=True)
                heading = card.find(["h2", "h3"])
                container = card
            if not link or not heading:
                continue
            title = heading.get_text(" ", strip=True)
            if not title_is_allowed(title, params.job_titles, params.excluded_title_terms):
                continue
            company_node = container.select_one(".company") if container else None
            href = str(link["href"])
            company_slug = href.split("/companies/", 1)[-1].split("/", 1)[0]
            text = container.get_text(" ", strip=True) if container else title
            jobs.append(
                JobPosting(
                    title=title,
                    company=company_node.get_text(" ", strip=True)
                    if company_node
                    else company_slug.replace("-", " ").title(),
                    url=urljoin(_URL, str(link["href"])),
                    location=text,
                    snippet=text[:3000],
                    source="Y Combinator Jobs",
                    source_url=_URL,
                    region=params.region_key,
                    search_query=f"YC jobs @ {params.region_key}",
                    company_type=CompanyType.STARTUP,
                )
            )
        return jobs
