"""Shared parser for public startup boards with company/job URL cards."""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from job_hunter.core.utils import title_is_allowed
from job_hunter.models import CompanyType, JobPosting, SearchParams


def parse_startup_jobs(html: str, base_url: str, source: str, params: SearchParams) -> list[JobPosting]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("article") or [
        link
        for link in soup.find_all("a", href=True)
        if "/companies/" in str(link["href"]) and "/jobs/" in str(link["href"])
    ]
    jobs: list[JobPosting] = []
    for card in cards[: params.max_results]:
        link = card if card.name == "a" else card.find("a", href=True)
        heading = card if card.name == "a" else card.find(["h2", "h3"])
        container = (card.find_parent(["li", "div"]) or card.parent) if card.name == "a" else card
        if not link or not heading:
            continue
        title = heading.get_text(" ", strip=True)
        if not title_is_allowed(title, params.job_titles, params.excluded_title_terms):
            continue
        href = str(link["href"])
        company_node = container.select_one(".company") if container else None
        company_slug = href.split("/companies/", 1)[-1].split("/", 1)[0]
        text = container.get_text(" ", strip=True) if container else title
        jobs.append(
            JobPosting(
                title=title,
                company=company_node.get_text(" ", strip=True)
                if company_node
                else company_slug.replace("-", " ").title(),
                url=urljoin(base_url, href),
                location=text,
                snippet=text[:3000],
                source=source,
                source_url=base_url,
                region=params.region_key,
                search_query=f"{source} @ {params.region_key}",
                company_type=CompanyType.STARTUP,
            )
        )
    return jobs
