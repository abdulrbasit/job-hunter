"""System-wide data contracts.

Types defined here are the canonical contract for job/profile/config data.
Some pipeline and serialization boundaries still pass `dict[str, Any]`
(job records flowing through scrape/score/gate stages) rather than these
models — that's pre-existing pipeline shape, not something this module
claims to have eliminated. Narrowing those remaining dict boundaries to
typed models is future cleanup, not required for new code to use these
types at the boundaries that already do.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class StoryBlock:
    story_id: str
    title: str
    role: str
    rating: str
    tags: list[str]
    summary: str
    text: str


# ---------------------------------------------------------------------------
# Job discovery
# ---------------------------------------------------------------------------


class JobPosting(BaseModel):
    """Canonical job record. Produced by sources, consumed by pipeline stages."""

    title: str
    company: str
    url: str
    location: str = ""
    country_code: str = ""
    snippet: str = ""
    source: str = ""
    posted_date_text: str = ""
    region: str = ""
    search_query: str = ""
    extraction_method: str = ""
    source_url: str = ""
    ats_platform: str = ""
    full_job_description: str = ""
    enrichment_source: str = ""
    posting_date_status: str = ""
    location_restrictions: list[str] = Field(default_factory=list)
    timezone_restrictions: list[float] = Field(default_factory=list)
    employment_type: str = ""
    seniority: list[str] = Field(default_factory=list)
    job_description_fetch_status: Literal["full", "thin", "fetch_failed", "page_noise", "position_closed", ""] = ""
    llm_posting_status_check: str = ""  # advisory: "open"|"closed"|"unknown" — set for posting_date_status="missing"


class Company(BaseModel):
    """Company record used in ATS discovery and career page scraping."""

    name: str
    career_url: str
    region: str
    location: str
    country: str = ""
    search_lang: str = ""
    ats: str = ""


class SearchParams(BaseModel):
    """Input contract for every JobSourceAdapter.fetch() call."""

    region_key: str
    country: str
    location: str
    search_lang: str
    job_titles: list[str]
    max_results: int = 50
    excluded_title_terms: list[str] = Field(default_factory=list)


class ScrapeStats(BaseModel):
    """Telemetry from a single scrape run."""

    total_fetched: int = 0
    total_after_dedup: int = 0
    total_after_policy: int = 0
    by_source: dict[str, int] = Field(default_factory=dict)
    accepted_by_source: dict[str, int] = Field(default_factory=dict)
    rejected_by_source: dict[str, dict[str, int]] = Field(default_factory=dict)
    failed_sources: list[str] = Field(default_factory=list)
    rejected: dict[str, int] = Field(default_factory=dict)
    duration_seconds: float = 0.0

    # Per-region observability (internal — no user-facing config; logs/telemetry only).
    fetched_by_region: dict[str, int] = Field(default_factory=dict)
    accepted_by_region: dict[str, int] = Field(default_factory=dict)
    rejected_by_region_reason: dict[str, dict[str, int]] = Field(default_factory=dict)
    accepted_by_region_source: dict[str, dict[str, int]] = Field(default_factory=dict)
    dead_by_source: dict[str, int] = Field(default_factory=dict)
    closed_by_source: dict[str, int] = Field(default_factory=dict)
    under_target_regions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline stage I/O
# ---------------------------------------------------------------------------


class HuntInput(BaseModel):
    """Entry point for the hunt pipeline."""

    region_key: str
    mode: Literal["agent", "llm-api"]
    from_snapshot: Path | None = None
    scrape_only: bool = False
    skip_score: bool = False
    skip_validate: bool = False
    force: bool = False
    depth: str = "standard"


class HuntOutput(BaseModel):
    """Result of a hunt pipeline run."""

    jobs: list[JobPosting] = Field(default_factory=list)
    stats: ScrapeStats = Field(default_factory=ScrapeStats)
    run_id: str = ""
    snapshot_path: Path | None = None  # active: consumed by llm-api --from-snapshot
    mode: Literal["agent", "llm-api"] = "agent"
