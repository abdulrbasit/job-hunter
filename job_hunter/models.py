"""System-wide data contracts.

Every package boundary uses types defined here. No raw dicts cross module
boundaries — callers must construct the appropriate model.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
    snippet: str = ""
    source: str = ""
    posted: str = ""
    region: str = ""
    query: str = ""
    extraction_method: str = ""
    source_url: str = ""
    ats_platform: str = ""
    full_jd: str = ""
    enrichment_source: str = ""
    date_status: str = ""
    location_restrictions: list[str] = Field(default_factory=list)
    timezone_restrictions: list[float] = Field(default_factory=list)
    employment_type: str = ""
    seniority: list[str] = Field(default_factory=list)
    fetch_status: Literal["full", "thin", "fetch_failed", "page_noise", "position_closed", ""] = ""
    # Set by score stage
    score: int | None = None
    matched_keywords: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


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
    snapshot_path: Path | None = None  # legacy: kept for llm-api --from-snapshot compat
    mode: Literal["agent", "llm-api"] = "agent"


class SnapshotPayload(BaseModel):
    """Serialised state written by --scrape-only, loaded by --from-snapshot."""

    jobs: list[JobPosting]
    region_key: str
    stats: ScrapeStats
    created_at: str  # ISO 8601


class JobScore(BaseModel):
    """Lightweight score summary for a job (used outside the full pipeline)."""

    score: int = Field(ge=0, le=100)
    matched_keywords: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    years_exp_required: int | None = None


class ScoreResult(BaseModel):
    """Output from the LLM scoring stage."""

    job_url: str
    fit_score: int = Field(ge=0, le=100)
    matched_keywords: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    years_exp_required: int | None = None
    recommendation: str = ""

    @field_validator("fit_score")
    @classmethod
    def clamp(cls, v: int) -> int:
        return max(0, min(100, v))


class TailorResult(BaseModel):
    """Output from the LLM tailoring stage."""

    job_url: str
    summary: str = ""
    bullets: dict[str, list[str]] = Field(default_factory=dict)
    projects: list[str] = Field(default_factory=list)
    skills_reorder: list[str] = Field(default_factory=list)


class CoverResult(BaseModel):
    """Output from the LLM cover letter stage."""

    job_url: str
    paragraphs: list[str]
    word_count: int


# ---------------------------------------------------------------------------
# LLM layer
# ---------------------------------------------------------------------------


class LLMRequest(BaseModel):
    """Input to the LLM client."""

    role: str  # "scoring" | "tailoring" | "cover_letter" | "linkedin" | ...
    prompt: str
    system: str | None = None
    max_tokens: int | None = None


class LLMResponse(BaseModel):
    """Output from the LLM client."""

    content: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


# ---------------------------------------------------------------------------
# Agent context
# ---------------------------------------------------------------------------


class AgentBatchContext(BaseModel):
    """Output from agent_context/batch.py — frozen 15-job slice for /job-hunter batch."""

    jobs: list[JobPosting]
    batch_id: str
    queued_count: int
    already_applied_titles: list[str] = Field(default_factory=list)


class ScoreContext(BaseModel):
    """Output from agent_context/score_context.py — input for /score skill."""

    job: JobPosting
    profile_summary: str
    story_index: list[StoryBlock]
    mode: Literal["snippet", "full"] = "snippet"


class BriefingContext(BaseModel):
    """Output from agent_context/briefing.py — input for /brief skill."""

    candidate_count: int
    by_source: dict[str, int]
    active_application_count: int
    latest_commit: str
    linkedin_posts_this_week: int
    linkedin_weekly_limit: int
