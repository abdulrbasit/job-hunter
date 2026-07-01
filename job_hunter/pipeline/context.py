"""Typed contracts for the pipeline runner — replaces the old raw `args: dict` / `int` boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from job_hunter.core.url_liveness import UrlLivenessCache


@dataclass
class PipelineCommandOptions:
    """One run's command-line intent. Mirrors the old orchestrator `args` dict shape 1:1."""

    mode: Literal["hunt", "tailor-links", "tailor-raw"]
    region: str | None = None
    depth: str = "standard"
    scrape_only: bool = False
    from_snapshot: str | None = None
    skip_score: bool = False
    skip_validate: bool = False
    force: bool = False
    links: str | None = None
    jd: str | None = None
    title: str | None = None
    company: str | None = None


@dataclass
class PipelineRunContext:
    """Config and shared state threaded through mode dispatch and stage functions."""

    options: PipelineCommandOptions
    api_cfg: dict[str, Any]
    scoring_cfg: dict[str, Any]
    max_years: int
    url_liveness: UrlLivenessCache
    start_ts: str
    start_mono: float


@dataclass
class PipelineResult:
    """Replaces the old bare `int` return code from orchestrator.run()."""

    exit_code: int
    jobs_found: int = 0
    jobs_processed: int = 0


@dataclass
class StageResult:
    """Typed kept/rejected split — the shape every screen/validate/gate stage already returns,
    now with a name attached instead of a bare tuple."""

    stage: str
    kept: list[dict[str, Any]]
    rejected: list[dict[str, Any]]


@dataclass
class ModeOutcome:
    """What a mode module hands back to the runner: either jobs to process, or a terminal result."""

    jobs: list[dict[str, Any]] = field(default_factory=list)
    existing_urls: set[str] = field(default_factory=set)
    existing_titles: set[str] = field(default_factory=set)
    early_result: PipelineResult | None = None
