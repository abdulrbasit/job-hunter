"""
Produces a tailored .tex resume per matched job.
Mirrors JD keywords in summary and bullets without fabricating metrics.
Tailoring strategy is configurable via config/job_hunter.yml.
"""

from __future__ import annotations

import logging
import re

from job_hunter.core.config import get_config, profile_path
from job_hunter.core.llm_utils import get_llm_role_settings
from job_hunter.llm.client import get_client as get_llm_client
from job_hunter.pipeline.llm_stage import LLMStage

logger = logging.getLogger(__name__)

with open(profile_path("resume_tex", "resume.tex"), encoding="utf-8") as f:
    BASE_TEX = f.read()

_SYSTEM_BASE = """You are editing a LaTeX resume.
Return ONLY the complete modified LaTeX file.
No markdown fences, no explanation, no commentary."""

# System prompt is built per-call from stable config-driven content so Anthropic can cache the prefix.
# Variable fields (keywords, tex, jd, gaps) stay in the user message.
PROMPT = """\
Mirror these JD keywords: {keywords}

BASE RESUME:
{tex}

JOB DESCRIPTION:
{jd}

GAPS (do not fabricate; simply do not emphasize):
{gaps}"""


def _build_tailoring_rules(tailoring_cfg: dict) -> str:
    """Build the strict tailoring rules section from job_hunter.yml."""
    tailoring = tailoring_cfg.get("tailoring", {})
    rules = tailoring.get("rules", {})

    lines = []

    forbidden = rules.get("forbidden_modifications", [])
    if forbidden:
        forbidden_text = ", ".join(m.replace("_", " ") for m in forbidden)
        lines.append(f"Do NOT: {forbidden_text}.")

    allowed = rules.get("allowed_modifications", [])
    if allowed:
        allowed_items = "; ".join(f"({chr(97 + i)}) {m.replace('_', ' ')}" for i, m in enumerate(allowed))
        lines.append(f"Only modify: {allowed_items}.")

    keyword_cfg = tailoring.get("keyword_strategy", {})
    aggressiveness = keyword_cfg.get("aggressiveness", "natural")
    avoid_kw = keyword_cfg.get("avoid_keywords", [])
    lines.append(f"Mirror JD keywords {aggressiveness}ly where context allows.")
    if avoid_kw:
        lines.append(f"Never introduce these terms: {', '.join(avoid_kw)}.")

    if rules.get("preserve_latex", True):
        lines.append("Keep all LaTeX commands and formatting intact.")
    lines.append("Return the complete .tex file.")

    return "\n".join(f"- {line}" for line in lines)


def _load_runtime_config() -> dict:
    """Load canonical runtime config with code-owned tailoring defaults."""
    return get_config("job_hunter")


def _load_story_bank(path_name: str) -> str:
    """Load story bank text for source-grounded tailoring."""
    try:
        path = profile_path("story_bank", path_name)
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("[tailor] Story bank not found; project tailoring disabled")
        return ""


def _load_career_context() -> str:
    try:
        return profile_path("career_context", "profile/career_context.md").read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _has_active_project_section(tex: str) -> bool:
    """True when a Projects section exists in uncommented LaTeX."""
    for line in tex.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            continue
        if re.search(r"\\(?:cv)?section\{(?:Selected\s+)?(?:Technical\s+)?Projects\}", stripped):
            return True
    return False


def _build_project_rules(tailoring_cfg: dict, tex: str, story_bank: str) -> str:
    rules = tailoring_cfg.get("tailoring", {}).get("rules", {}).get("projects", {})
    max_projects = rules.get("max_projects", 4)
    min_bullets = rules.get("min_bullets_per_project", 3)
    max_bullets = rules.get("max_bullets_per_project", 5)
    page_limit = rules.get("max_total_resume_pages", 2)

    active_projects = _has_active_project_section(tex)
    has_story_bank = bool(story_bank.strip())

    if not active_projects:
        return (
            "- No active Projects/Technical Projects section exists in the LaTeX resume. "
            "Do not add, uncomment, or tailor project content."
        )
    if not has_story_bank:
        return "- The story bank is missing or empty. Keep the existing project section unchanged."

    return "\n".join(
        [
            "- Tailor projects only if an active, uncommented Projects/Technical Projects section already exists in the resume.",
            "- Never uncomment a commented project section and never add a project section solely to fill space.",
            "- Use only verified project material from the story bank.",
            "- Select projects only when they are relevant to the job description; otherwise keep or reduce the section rather than filling space.",
            f"- Include at most {max_projects} projects total.",
            f"- Each included project must have {min_bullets}-{max_bullets} bullets. Never exceed {max_bullets} bullets for a project.",
            "- Prioritize PM/PO-relevant evidence: product vision, requirements, stakeholder/user workflow, prioritization, analytics/KPIs, technical trade-offs, validation, and impact.",
            f"- The complete resume must remain at {page_limit} pages or fewer. Do not create a third page.",
            "- If project content risks overflow, remove the least relevant project or shorten bullets before changing other sections.",
            "- For double-column resumes, the second page project section must remain single-column if it is already single-column.",
            "- For single-column resumes, apply the same relevance, project count, bullet count, and page-limit rules.",
        ]
    )


def _build_positioning_rules(tailoring_cfg: dict) -> str:
    rules = tailoring_cfg.get("tailoring", {}).get("rules", {})
    summary = rules.get("summary", {})
    bullets = rules.get("bullets", {})
    lines = []

    max_lines = summary.get("max_lines")
    if max_lines:
        lines.append(f"- Keep the summary to {max_lines} lines or fewer.")
    if summary.get("no_em_dashes"):
        lines.append("- Do not use em dashes in the summary.")

    for preference in summary.get("proof_point_preferences", []):
        lines.append(f"- {preference}")

    max_bullets = bullets.get("max_per_role")
    if max_bullets:
        lines.append(f"- Keep each role to at most {max_bullets} bullets.")

    return "\n".join(lines) if lines else "- Follow the existing summary and bullet constraints."


def tailor(match_result: dict) -> str:
    """
    Tailor the base resume for a specific job.

    Args:
        match_result: Scored match dict with job, matched_keywords, gaps.

    Returns:
        Modified LaTeX resume text (falls back to BASE_TEX on error).
    """
    job = match_result["job"]
    keywords = ", ".join(match_result.get("matched_keywords", []))
    gaps = ", ".join(match_result.get("gaps", []))
    tailoring_cfg = _load_runtime_config()
    stories_cfg = tailoring_cfg.get("tailoring", {}).get("stories", {})
    story_bank = _load_story_bank(stories_cfg.get("story_bank", "story_bank.md"))
    career_context = _load_career_context()
    story_bank_limit = int(stories_cfg.get("max_chars_for_tailoring", 16000))
    tailoring_rules = _build_tailoring_rules(tailoring_cfg)
    positioning_rules = _build_positioning_rules(tailoring_cfg)
    project_rules = _build_project_rules(tailoring_cfg, BASE_TEX, story_bank)

    stage = LLMStage(
        "tailoring",
        cache_system=True,
        cache_ttl="1h",
        client_factory=get_llm_client,
        settings_factory=get_llm_role_settings,
    )

    system = "\n\n".join(
        [
            _SYSTEM_BASE,
            f"TAILORING RULES:\n{tailoring_rules}",
            f"POSITIONING RULES:\n{positioning_rules}",
            f"PROJECT SECTION RULES:\n{project_rules}",
            f"CAREER CONTEXT:\n{career_context[:4000] if career_context else '(career context unavailable)'}",
            f"STORY BANK SOURCE MATERIAL:\n{story_bank[:story_bank_limit] if story_bank else '(story bank unavailable)'}",
        ]
    )

    prompt = PROMPT.format(
        keywords=keywords,
        tex=BASE_TEX,
        jd=job["snippet"],
        gaps=gaps,
    )

    try:
        tailored_text = stage.complete(
            system=system,
            user=prompt,
        )
        logger.info(f"[tailor] Tailored for {job.get('title', '?')} @ {job.get('company', '?')}")

        if not tailored_text.startswith("\\"):
            logger.warning("[tailor] Response does not appear to be LaTeX.")

        return tailored_text
    except Exception as e:
        logger.error(f"[tailor] Error: {e} — returning base resume")
        return BASE_TEX
