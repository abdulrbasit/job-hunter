"""
Generates a cover letter (markdown) for each matched job.
Configurable via config/job_hunter.yml.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime

from job_hunter.core.config import ROOT, get_config, profile_path
from job_hunter.core.llm_utils import get_llm_role_settings
from job_hunter.llm.client import get_client as get_llm_client
from job_hunter.pipeline.llm_stage import LLMStage

logger = logging.getLogger(__name__)

ROOT = str(ROOT)

# Load only the refined STAR stories section when present to avoid story-format
# examples being echoed in generated letters.
with open(profile_path("story_bank", "story_bank.md"), encoding="utf-8") as f:
    _raw_stories = f.read()

_FINAL_MARKER = "## Final — refined STAR stories"
_marker_idx = _raw_stories.find(_FINAL_MARKER)
if _marker_idx == -1:
    _marker_idx = _raw_stories.find("## Final - refined STAR stories")
STORIES = _raw_stories[_marker_idx:] if _marker_idx != -1 else _raw_stories


def _config_section(config: dict, name: str, default: dict | None = None) -> dict:
    """Read a section from either legacy top-level or nested cover_letter config."""
    if name in config:
        return config.get(name) or {}
    return (config.get("cover_letter", {}) or {}).get(name, default or {}) or {}


def _clean_body(body: str) -> str:
    """Remove citation-like story IDs if a model echoes them despite the prompt."""
    body = re.sub(r"\s*\[[A-Z][A-Z0-9_ -]*-\d+\]", "", body)
    return body.strip()


def load_runtime_config() -> dict[str, object]:
    logger.info("[cover] Loaded runtime configuration")
    return get_config("job_hunter")


def _build_system(cover_cfg: dict, candidate_background: str, story_limit: int) -> str:
    """Build the system prompt from code-owned cover-letter defaults."""
    tone_list = cover_cfg.get("tone", []) or []
    tone_text = ", ".join(tone_list) if tone_list else "formal, confident, and substantive"

    forbidden_cfg = cover_cfg.get("forbidden", {}) or {}
    style_rules = forbidden_cfg.get("style", []) or []
    forbidden_phrases = forbidden_cfg.get("phrases", []) or []

    rules_lines = [f"- {rule}" for rule in style_rules]
    if forbidden_phrases:
        phrases_str = ", ".join(f'"{p}"' for p in forbidden_phrases)
        rules_lines.append(f"- Forbidden phrases: {phrases_str}")
    # Output format rules — always required, not config-driven
    rules_lines += [
        "- No story IDs or bracketed citations, such as [STORY-01] or similar tags",
        "- No sender details, address blocks, contact information, or Re: subject lines",
        "- Return plain text only. No markdown, no headers, no bullet points.",
        "- Start directly with the first sentence of the letter body.",
    ]

    content_cfg = cover_cfg.get("content", {}) or {}
    max_words = int(content_cfg.get("max_words", 280))
    target_words = int(content_cfg.get("target_words", 220))
    paragraphs = int(content_cfg.get("paragraphs", 4))

    return "\n\n".join(
        [
            f"You write professional cover letters for job applications.\n\n"
            f"Tone: {tone_text}.\n\n"
            f"Hard rules — no exceptions:\n" + "\n".join(rules_lines),
            f"LENGTH: target {target_words} words, hard maximum {max_words} words, {paragraphs} paragraphs.",
            f"CANDIDATE BACKGROUND:\n{candidate_background}",
            f"STORY LIBRARY — use these facts and metrics exactly as stated, do not embellish:\n{STORIES[:story_limit]}",
        ]
    )


def _build_user_prompt(cover_cfg: dict, jd: str, company: str, title: str) -> str:
    """Build the user message from the cover_letter structure section."""
    structure = cover_cfg.get("structure", {}) or {}
    content_cfg = cover_cfg.get("content", {}) or {}
    paragraphs_count = int(content_cfg.get("paragraphs", 4))

    para_lines = []
    for i in range(1, paragraphs_count + 1):
        para = structure.get(f"paragraph_{i}", {}) or {}
        name = para.get("name", f"Paragraph {i}")
        max_sentences = para.get("max_sentences", 3)
        purpose = para.get("purpose", "")
        para_lines.append(f"PARAGRAPH {i} — {name} (max {max_sentences} sentences): {purpose}")

    structure_text = "\n".join(para_lines)

    return (
        f"Write a professional cover letter body for this job application.\n\n"
        f"Structure ({paragraphs_count} paragraphs, plain text, no paragraph labels):\n"
        f"{structure_text}\n\n"
        f"Every factual claim must be directly traceable to the story library. "
        f"Do not infer, extrapolate, or combine claims.\n\n"
        f"JOB DESCRIPTION:\n{jd}\n\n"
        f"COMPANY: {company}\n"
        f"ROLE: {title}"
    )


def _candidate_background(config: dict) -> str:
    try:
        career_context = profile_path("career_context", "profile/career_context.md").read_text(encoding="utf-8")
    except OSError:
        career_context = ""
    background = career_context.strip()
    return background or "Candidate career context is unavailable; use only the resume and verified story library."


def write_cover(
    match_result: dict,
    output_dir: str,
    config: dict | None = None,
) -> str:
    """
    Generate a cover letter (markdown) for a matched job.
    Returns the path to the saved cover_letter.md.
    """
    if config is None:
        config = load_runtime_config()

    job = match_result["job"]
    stage = LLMStage(
        "cover_letter",
        cache_system=True,
        cache_ttl="1h",
        client_factory=get_llm_client,
        settings_factory=get_llm_role_settings,
    )

    header_config = _config_section(config, "header")
    if header_config.get("include_date", True):
        date_format = header_config.get("date_format", "%B %d, %Y")
        today = datetime.today().strftime(date_format).replace(" 0", " ")
    else:
        today = ""

    logger.info(f"[cover] Generating for {job['title']} @ {job['company']}")

    candidate_background = _candidate_background(config)

    cover_cfg = config.get("cover_letter", {}) or {}
    stories_cfg = cover_cfg.get("stories", {}) or {}
    story_limit = int(stories_cfg.get("max_chars_for_cover", 6000))

    # System prompt is assembled from stable content (rules + background + story bank)
    # so Anthropic can cache the prefix across sequential cover-letter calls in the same run.
    # Variable content (JD, company, title) stays in the user message.
    system = _build_system(cover_cfg, candidate_background, story_limit)
    prompt = _build_user_prompt(cover_cfg, job["snippet"], job["company"], job["title"])

    try:
        body = stage.complete(
            system=system,
            user=prompt,
        )
        body = _clean_body(body)
        logger.debug(f"[cover] Generated body ({len(body)} chars)")
    except Exception as e:
        logger.error(f"[cover] Error generating cover letter: {e}")
        raise

    header = _config_section(config, "header")
    salutation = header.get("salutation", "Dear Hiring Manager,")
    closing = _config_section(config, "closing")
    closing_format = closing.get("format", "Best regards,\nCandidate Name")

    date_line = f"{today}\n" if today else ""
    letter = f"{date_line}{salutation}\n\n{body}\n\n{closing_format}"

    md_path = os.path.join(output_dir, "cover_letter.md")
    try:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(letter)
        logger.info(f"[cover] Saved: {md_path}")
    except Exception as e:
        logger.error(f"[cover] Error saving markdown: {e}")
        raise

    return md_path
