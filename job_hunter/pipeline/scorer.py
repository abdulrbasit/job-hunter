"""
Score each job against the base resume using an LLM.
Scoring criteria are configurable via config/job_hunter.yml.
"""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from job_hunter.config.loader import get_api_config, get_config, profile_path
from job_hunter.constants import LLM_REPAIR_INPUT_CHARS
from job_hunter.core.latex_utils import compact_latex_resume as _compact_latex_resume
from job_hunter.core.llm_utils import get_llm_role_settings
from job_hunter.llm.client import get_client as get_llm_client
from job_hunter.pipeline.llm_stage import LLMStage

logger = logging.getLogger(__name__)


def load_runtime_config() -> dict[str, object]:
    """Load canonical runtime config with code-owned scoring defaults."""
    logger.info("[scorer] Loaded runtime configuration")
    return get_config("job_hunter")


_SYSTEM_BASE = (
    "You are a recruiter scoring job fit. "
    "Return ONLY valid JSON with no markdown fences, no explanation. "
    'Schema: {"score": int, "matched_keywords": [str], "gaps": [str], '
    '"years_exp_required": int or null, "role_summary": str, "score_rationale": str} '
    "Base your score only on evidence present in the provided resume. "
    "Do not infer unstated skills, experience, or qualifications."
)


def _build_system_with_resume(config: dict) -> str:
    """Build the system prompt with the resume embedded so Anthropic can cache the prefix."""
    with open(profile_path("resume_tex", "resume.tex"), encoding="utf-8") as f:
        base_resume = f.read()
    resume_context = build_scoring_resume_context(base_resume, config)
    return f"{_SYSTEM_BASE}\n\nCANDIDATE RESUME:\n{resume_context}"


def _build_scoring_prompt(jd_context: str, config: dict) -> str:
    """Build the scoring user prompt from config values."""
    prompt_cfg = _scoring_prompt_config(config)
    max_kw = int(prompt_cfg.get("max_matched_keywords", 10))
    max_gaps = int(prompt_cfg.get("max_gaps", 5))
    return (
        f"Score this candidate's resume against the job description.\n\n"
        f"JOB DESCRIPTION:\n{jd_context}\n\n"
        f"Rules:\n"
        f"- score: 0-100 fit score\n"
        f"- matched_keywords: up to {max_kw} keywords from JD present in resume\n"
        f"- gaps: up to {max_gaps} skills in JD missing from resume\n"
        f"- years_exp_required: years of experience stated in JD, null if not mentioned\n"
        f"- role_summary: one sentence describing what this role requires\n"
        f"- score_rationale: one sentence explaining why this score was assigned\n\n"
        f"Return JSON only."
    )


REPAIR_PROMPT = """\
Convert this model response into valid JSON matching exactly this schema:
{{"score": int, "matched_keywords": [str], "gaps": [str], "years_exp_required": int|null, "role_summary": str, "score_rationale": str}}

Rules:
- Return ONLY valid JSON.
- If a field is missing or unclear, use score=0, matched_keywords=[], gaps=["parse repair"], years_exp_required=null, role_summary="", score_rationale="parse repair".

Response:
{raw}
"""


def _scoring_prompt_config(config: dict) -> dict:
    scoring = config.get("scoring", {}) or {}
    return scoring.get("prompt_context", {}) or {}


def build_scoring_resume_context(resume: str, config: dict) -> str:
    prompt_cfg = _scoring_prompt_config(config)
    mode = str(prompt_cfg.get("resume_mode", "compact_text"))
    max_chars = int(prompt_cfg.get("resume_max_chars", 4500))

    context = _compact_latex_resume(resume) if mode == "compact_text" else resume
    return context[:max_chars]


def build_scoring_job_context(job: dict, config: dict) -> str:
    prompt_cfg = _scoring_prompt_config(config)
    max_chars = int(prompt_cfg.get("job_description_max_chars", 5000))
    return str(job.get("snippet", ""))[:max_chars]


def score(job: dict, config: dict) -> dict:
    stage = LLMStage(
        "scoring",
        response_format="json",
        cache_system=True,
        cache_ttl="5m",
        client_factory=get_llm_client,
        settings_factory=get_llm_role_settings,
    )
    system = _build_system_with_resume(config)
    jd_context = build_scoring_job_context(job, config)
    prompt = _build_scoring_prompt(jd_context, config)

    raw = ""
    try:
        raw = stage.complete(
            system=system,
            user=prompt,
        )
        try:
            result = stage.parse_json_object(raw, "scoring response must be a JSON object")
        except (json.JSONDecodeError, ValueError):
            logger.info("[scorer] Repairing malformed score JSON for %s", job.get("title", "Unknown"))
            repaired = stage.complete(
                system=system,
                user=REPAIR_PROMPT.format(raw=raw[:LLM_REPAIR_INPUT_CHARS]),
            )
            result = stage.parse_json_object(repaired, "scoring response must be a JSON object")
        logger.debug(f"[scorer] {job.get('title', 'Unknown')} → score={result.get('score')}")
    except ImportError:
        raise  # missing SDK affects every job — let score_and_filter_jobs fail fast
    except json.JSONDecodeError as e:
        logger.error(f"[scorer] JSON parse error: {e} | raw: {raw[:200]!r}")
        result = {
            "score": 0,
            "matched_keywords": [],
            "gaps": ["parse error"],
            "years_exp_required": None,
        }
    except Exception as e:
        logger.error(f"[scorer] API error: {e}")
        result = {
            "score": 0,
            "matched_keywords": [],
            "gaps": ["api error"],
            "years_exp_required": None,
        }

    result["job"] = job
    return result


def strategic_override(job: dict, config: dict) -> dict | None:
    """Return the matching strategic override, if one applies."""
    overrides = config.get("scoring", {}).get("strategic_overrides", [])
    job_company = job.get("company", "").lower()

    for override in overrides:
        company = override.get("company", "").lower()
        if company and company in job_company:
            logger.info(
                f"[scorer] Strategic override for {job['company']}: {override.get('reason', 'strategic override')}"
            )
            return override

    return None


def check_strategic_override(job: dict, config: dict) -> int | None:
    """
    Check if a job matches a strategic override.
    Returns min_score_override or None if no override applies.
    """
    override = strategic_override(job, config)
    if override is None:
        return None
    return override.get("min_score_override")


def strategic_override_companies(config: dict) -> list[str]:
    """Return strategic companies whose overrides bypass the max-years filter."""
    return [
        str(override.get("company", "")).strip()
        for override in config.get("scoring", {}).get("strategic_overrides", [])
        if str(override.get("company", "")).strip() and override.get("bypass_max_years_experience", False)
    ]


def score_and_filter_jobs(
    jobs: list[dict],
    min_score: int | None = None,
    max_years: int | None = None,
    config: dict | None = None,
) -> list[dict]:
    """
    Score all jobs and return only those meeting the threshold.

    Args:
        jobs:      List of job postings to score.
        min_score: Minimum score override (reads from config if None).
        max_years: Max years of experience override (reads from config if None).
        config:    Scoring config dict (loads from file if None).

    Returns:
        List of scored match dicts for jobs that passed the threshold.
    """
    if config is None:
        config = load_runtime_config()

    scoring_settings = config.get("scoring", {})
    if min_score is None:
        min_score = scoring_settings.get("min_fit_score", 70)
    if max_years is None:
        max_years = scoring_settings.get("max_years_experience_required", 4)
    logger.info(f"[scorer] Filtering jobs: min_score={min_score}, max_years={max_years}")

    # Fail fast if the LLM SDK isn't installed rather than silently scoring everything 0.
    try:
        get_llm_client("scoring")
    except ImportError as e:
        logger.error(f"[scorer] Cannot initialise scoring client — SDK missing: {e}")
        raise

    api_cfg = get_api_config()
    max_workers = int(api_cfg.get("llm", {}).get("max_workers", 5))

    counter = 0
    counter_lock = threading.Lock()

    def _score_job(job: dict) -> dict | None:
        nonlocal counter
        with counter_lock:
            counter += 1
            idx = counter
        label = f"{job['title']} @ {job['company']}"
        prefix = f"[scorer] [{idx}/{len(jobs)}] {label}"
        logger.info(f"{prefix}: scoring...")
        result = score(job, config)
        score_val = result["score"]
        yrs = result.get("years_exp_required")
        logger.info(f"{prefix}: score={score_val}, years_required={yrs}")
        override = strategic_override(job, config)
        override_min = override.get("min_score_override") if override else None
        effective_min = override_min if override_min is not None else min_score
        if score_val < effective_min:
            logger.debug(f"{prefix}: skipped, score {score_val} below threshold {effective_min}")
            return None
        bypass_max_years = bool(override and override.get("bypass_max_years_experience", False))
        if yrs is not None and yrs > max_years and not bypass_max_years:
            logger.debug(f"{prefix}: skipped, years required ({yrs}) exceeds maximum ({max_years})")
            return None
        logger.info(f"{prefix}: matched")
        # Normalise to canonical score.yml schema
        result["decision"] = "APPLY"
        result["matched"] = result.pop("matched_keywords", [])
        result["matched_story_ids"] = []  # ponytail: LLM API scorer doesn't consult story bank
        result["role_summary"] = result.get("role_summary", "")
        result["score_rationale"] = result.get("score_rationale", "")
        result["recommendation"] = "Apply"
        return result

    matched = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for result in executor.map(_score_job, jobs):
            if result is not None:
                matched.append(result)

    logger.info(f"[scorer] {len(matched)}/{len(jobs)} jobs matched threshold")
    return matched
