"""Per-batch and per-match processing: screen, validate, score, tailor, cover, PDF, finalize."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from functools import cache
from pathlib import Path
from typing import Any

from job_hunter.config.loader import ROOT as REPO_ROOT
from job_hunter.config.loader import get_config, profile_path
from job_hunter.constants import DEFAULT_BATCH_SIZE
from job_hunter.core.url_liveness import UrlLivenessCache
from job_hunter.pipeline import _match_processor
from job_hunter.pipeline._artifacts import write_match_artifacts
from job_hunter.pipeline.cover_writer import write_cover
from job_hunter.pipeline.pdf_compiler import compile_tex
from job_hunter.pipeline.quality_gate import apply_pre_scoring_quality_gate
from job_hunter.pipeline.stages.readme import slugify
from job_hunter.pipeline.stages.readme import update_readme as write_readme_table
from job_hunter.pipeline.stages.scoring import score_and_filter_jobs, strategic_override_companies
from job_hunter.pipeline.stages.screening import screen_jobs_by_rules
from job_hunter.pipeline.stages.validation import validate
from job_hunter.pipeline.tailorer import tailor
from job_hunter.sources.policy import JobPolicy
from job_hunter.tracking.applications import upsert_application_from_job

logger = logging.getLogger(__name__)

ROOT = str(REPO_ROOT)


@cache
def _jobs_dir() -> Path:
    d = profile_path("output_dir", "outputs/jobs")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _today() -> str:
    return datetime.today().strftime("%Y-%m-%d")


def update_readme(matches: list[dict[str, Any]]) -> None:
    write_readme_table(matches, ROOT, _today())


def _lang_profile_path(lang: str) -> Callable[[str, str], Path]:
    """profile_path lookalike bound to the resume entry serving `lang` — per-language
    latex_class/profile_image overrides flow into asset copying and tex rewriting.
    Falls back to the plain profile_path (base entry / legacy semantics) whenever the
    map form isn't configured or the entry leaves the key empty."""
    from job_hunter.config.loader import get_job_hunter_config
    from job_hunter.config.resumes import resume_spec_for

    profile = get_job_hunter_config().get("profile", {})
    _chosen, spec = resume_spec_for(profile, lang)
    map_form = isinstance(profile.get("resumes"), dict)

    def resolver(key: str, default: str) -> Path:
        value = spec.get(key, "")
        if map_form and value:
            path = Path(value)
            return path if path.is_absolute() else REPO_ROOT / path
        return profile_path(key, default)

    return resolver


def _copy_latex_assets(job_dir: Path, lang: str = "") -> None:
    _match_processor.copy_latex_assets(job_dir, _lang_profile_path(lang))


def _screen_by_config(
    jobs: list[dict[str, Any]], scoring_config: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply deterministic exclusion rules from config before any LLM calls."""
    return screen_jobs_by_rules(jobs, scoring_config)


def _write_company_research(job: dict[str, Any], job_dir: Path) -> None:
    from job_hunter.llm.stage import LLMStage

    _match_processor.write_company_research(
        job,
        job_dir,
        get_config=get_config,
        llm_stage_factory=LLMStage,
        logger=logger,
    )


def _make_generated_tex_self_contained(tex: str, lang: str = "") -> str:
    return _match_processor.make_generated_tex_self_contained(tex, _lang_profile_path(lang))


def _process_match(match: dict[str, Any]) -> bool:
    return _match_processor.process_match(
        match,
        today=_today,
        jobs_dir=_jobs_dir(),
        slugify=slugify,
        write_match_artifacts=write_match_artifacts,
        write_company_research=_write_company_research,
        tailor=tailor,
        make_tex_self_contained=_make_generated_tex_self_contained,
        copy_latex_assets=_copy_latex_assets,
        compile_tex=compile_tex,
        write_cover=write_cover,
        logger=logger,
    )


def _configured_batch_size(config: dict[str, Any]) -> int:
    """Return the shared agent/LLM-API batch size from canonical config."""
    scoring = config.get("scoring")
    if not isinstance(scoring, dict) or "batch_size" not in scoring:
        return DEFAULT_BATCH_SIZE
    batch_size = int(scoring["batch_size"])
    if batch_size < 1:
        raise ValueError("scoring.batch_size must be at least 1")
    return batch_size


def process_jobs(
    jobs: list[dict[str, Any]],
    *,
    skip_validate: bool,
    skip_score: bool,
    max_years: int,
    api_config: dict[str, Any],
    scoring_config: dict[str, Any],
    url_checker: Any = None,
) -> list[dict[str, Any]]:
    """
    Shared downstream pipeline: validate, score, tailor, cover, PDF.
    Returns the list of successfully processed match dicts.
    """
    jobs, config_rejected = _screen_by_config(jobs, scoring_config)
    for job in config_rejected:
        logger.info(
            "  Objective screen rejected: %s @ %s: %s",
            job.get("title"),
            job.get("company"),
            job.get("_rejection_reason"),
        )
    if not jobs:
        logger.warning("[pipeline] All jobs rejected by config exclusion rules.")
        return []

    if not skip_validate:
        logger.info("[pipeline] Validating %s job(s)...", len(jobs))
        jobs, rejected = validate(
            jobs,
            max_years=max_years,
            api_config=api_config,
            url_checker=url_checker or UrlLivenessCache().is_alive,
            max_years_bypass_companies=strategic_override_companies(scoring_config),
            excluded_industries=JobPolicy(scoring_config).excluded_industries,
        )
        for job in rejected:
            logger.info(
                "  Rejected: %s @ %s: %s",
                job.get("title"),
                job.get("company"),
                job.get("_rejection_reason"),
            )
        if not jobs:
            logger.warning("[pipeline] All jobs rejected during validation.")
            return []
        logger.info("[pipeline] %s job(s) passed validation", len(jobs))
    else:
        logger.info("[pipeline] Validation skipped (--skip-validate)")

    if skip_score:
        logger.info("[pipeline] Scoring skipped (--skip-score) - processing all")
        matches = [{"job": job, "score": 0, "matched_keywords": [], "gaps": []} for job in jobs]
    else:
        jobs, gate_rejected = apply_pre_scoring_quality_gate(jobs, scoring_config)
        if gate_rejected:
            logger.info("[pipeline] Quality gate dropped %s job(s) (rank/cap)", len(gate_rejected))
        if not jobs:
            logger.warning("[pipeline] Quality gate rejected all remaining jobs.")
            return []
        logger.info("[pipeline] Scoring %s job(s)...", len(jobs))
        matches = score_and_filter_jobs(jobs, config=scoring_config)
        if not matches:
            logger.warning("[pipeline] No jobs passed the scoring threshold.")
            return []
        logger.info("[pipeline] %s job(s) passed scoring", len(matches))

    batch_size = _configured_batch_size(scoring_config)
    if len(matches) > batch_size:
        matches = sorted(matches, key=lambda match: match.get("score", 0), reverse=True)
        logger.info(
            "[pipeline] Batch size: tailoring top %s of %s matched job(s)",
            batch_size,
            len(matches),
        )
        matches = matches[:batch_size]

    logger.info("[pipeline] Processing %s matched job(s)...", len(matches))
    processed = []
    for idx, match in enumerate(matches, 1):
        job = match["job"]
        logger.info(
            "[pipeline] [%s/%s] %s @ %s (score=%s)",
            idx,
            len(matches),
            job["title"],
            job["company"],
            match["score"],
        )
        try:
            if _process_match(match):
                processed.append(match)
        except Exception as e:
            logger.error("  Unexpected error: %s", e, exc_info=True)

    return processed


def finalize_processed_batch(processed: list[dict[str, Any]], existing_urls: set[str]) -> None:
    """Persist successful artifacts as tailored applications and refresh README.

    One bad match (e.g. a race on score.yml) must not abort the upsert for the
    rest of the batch — each upsert is isolated, matching the "one bad item
    doesn't abort the batch" pattern used elsewhere in this pipeline."""
    if not processed:
        return
    logger.info("[pipeline] Updating README and tracker...")
    for match in processed:
        job = match["job"]
        slug = f"{_today()}_{slugify(job['company'])}_{slugify(job['title'])}"
        try:
            upsert_application_from_job(slug, root=Path(ROOT), status="tailored")
        except Exception:
            logger.exception("[pipeline] Could not record application for %s", slug)
    update_readme(processed)
