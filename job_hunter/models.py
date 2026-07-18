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
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class LocationScope(StrEnum):
    CITY = "city"
    COUNTRY = "country"
    REMOTE_COUNTRY = "remote_country"
    REMOTE_GLOBAL = "remote_global"


class PostingType(StrEnum):
    INTERNSHIP = "internship"
    WORKING_STUDENT = "working_student"
    THESIS = "thesis"
    GRADUATE_PROGRAM = "graduate_program"
    TRAINEE = "trainee"


class CompanyType(StrEnum):
    STARTUP = "startup"
    SCALEUP = "scaleup"
    SME = "sme"
    ENTERPRISE = "enterprise"
    UNKNOWN = "unknown"


class FundingStage(StrEnum):
    PRE_SEED = "pre_seed"
    SEED = "seed"
    SERIES_A = "series_a"
    SERIES_B = "series_b"
    SERIES_C_PLUS = "series_c_plus"
    GROWTH = "growth"
    BOOTSTRAPPED = "bootstrapped"


class CanonicalCity(BaseModel):
    """Stable city identity from package-owned bundled data."""

    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    population: int = 0


class Location(BaseModel):
    """Canonical geographic scope used by config, sources, and pipeline gates."""

    country: str = ""
    scope: LocationScope
    city: CanonicalCity | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> Location:
        self.country = self.country.strip().upper()
        if self.scope == LocationScope.REMOTE_GLOBAL:
            if self.country or self.city is not None:
                raise ValueError("remote_global cannot include a country or city")
        elif len(self.country) != 2:
            raise ValueError("country must be an ISO alpha-2 code")
        if self.scope == LocationScope.CITY and self.city is None:
            raise ValueError("city scope requires a city")
        if self.scope != LocationScope.CITY and self.city is not None:
            raise ValueError("only city scope can include a city")
        return self

    @property
    def id(self) -> str:
        if self.scope == LocationScope.REMOTE_GLOBAL:
            return "remote:global"
        if self.scope == LocationScope.CITY and self.city is not None:
            return f"city:{self.country}:{self.city.id}"
        return f"{self.scope.value}:{self.country}"


class JobPosting(BaseModel):
    """Canonical job record. Produced by sources, consumed by pipeline stages."""

    title: str
    company: str
    url: str
    location: str = ""
    country_code: str = ""
    canonical_locations: list[Location] = Field(default_factory=list)
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
    posting_type: PostingType | None = None
    company_type: CompanyType = CompanyType.UNKNOWN
    funding_stage: FundingStage | None = None
    experience_unknown: bool = False
    seniority: list[str] = Field(default_factory=list)
    job_description_fetch_status: Literal["full", "thin", "fetch_failed", "page_noise", "position_closed", ""] = ""
    llm_posting_status_check: str = ""  # advisory: "open"|"closed"|"unknown" — set for posting_date_status="missing"


class Company(BaseModel):
    """Company record used in ATS discovery and career page scraping."""

    name: str
    career_url: str
    catalog_id: str = ""
    region: str = ""
    location: str = ""
    country: str = ""
    city: str = ""
    industry: str = "other"
    search_lang: str = ""
    ats: str = ""
    company_type: CompanyType = CompanyType.UNKNOWN
    funding_stage: FundingStage | None = None


class FilterMatchMode(StrEnum):
    EXACT = "exact"
    CONTAINS = "contains"
    REGEX = "regex"


class FilterType(BaseModel):
    """Package-owned definition bound to scalar choices from job_hunter.yml."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    mode: FilterMatchMode
    normalize_company: bool = False
    taxonomy: str = ""


class Industry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    aliases: list[str] = Field(default_factory=list)


class FilterCatalog(BaseModel):
    """Typed package-owned taxonomy backing user filter choices."""

    model_config = ConfigDict(extra="forbid")

    version: int
    employment_types: list[str]
    industries: list[Industry]


class ExperienceLevel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    track: Literal["student", "ic", "management"]
    min_years: int
    max_years: int | None = None
    keywords: dict[str, list[str]] = Field(default_factory=dict)


class ExperienceLevelCatalog(BaseModel):
    """Typed package-owned taxonomy of experience levels backing filters.experience_levels."""

    model_config = ConfigDict(extra="forbid")

    version: int
    levels: list[ExperienceLevel]


class JobTitleCatalog(BaseModel):
    """Typed package-owned list of common job titles backing the job-titles autocomplete."""

    model_config = ConfigDict(extra="forbid")

    version: int
    titles: list[str]


class SearchParams(BaseModel):
    """Input contract for every JobSourceAdapter.fetch() call."""

    region_key: str
    canonical_location: Location | None = None
    country: str
    location: str
    search_lang: str
    job_titles: list[str]
    max_results: int = 50
    excluded_title_terms: list[str] = Field(default_factory=list)
    query_terms: list[str] = Field(default_factory=list)
    student_mode: bool = False


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
    from_db_candidates: bool = False
    scrape_only: bool = False
    skip_score: bool = False
    skip_validate: bool = False
    force: bool = False
    depth: str = "standard"

    @model_validator(mode="after")
    def validate_candidate_source(self) -> HuntInput:
        selected = sum((self.from_snapshot is not None, self.from_db_candidates, self.scrape_only))
        if selected > 1:
            raise ValueError("--from-db-candidates, --from-snapshot, and --scrape-only are mutually exclusive")
        if self.from_db_candidates and self.mode != "llm-api":
            raise ValueError("--from-db-candidates requires llm-api mode; agent mode uses /job-hunter batch")
        return self


class HuntOutput(BaseModel):
    """Result of a hunt pipeline run."""

    jobs: list[JobPosting] = Field(default_factory=list)
    stats: ScrapeStats = Field(default_factory=ScrapeStats)
    run_id: str = ""
    snapshot_path: Path | None = None  # active: consumed by llm-api --from-snapshot
    mode: Literal["agent", "llm-api"] = "agent"
