"""Generate public-safe LinkedIn raw ideas from the confidential story bank."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from job_hunter.config.loader import setup_logging
from job_hunter.linkedin._config import (
    append_section,
    complete_linkedin,
    configured_path,
    extract_json,
    format_yaml_list,
    linkedin_enabled,
    load_linkedin_config,
    next_idea_id,
    read_text,
    story_bank_text,
)

logger = setup_logging(log_level=os.environ.get("LOG_LEVEL", "INFO"))

SYSTEM = """You create LinkedIn content ideas from confidential career notes.
Return JSON only. Do not include markdown fences."""

PROMPT = """Create {count} public-safe LinkedIn raw ideas.

The story bank is confidential private inspiration. Do not reveal internal
product names, unreleased details, private metrics, team structures, incidents,
stakeholder names, or anything marked as forbidden.

Transform private details into general lessons for the configured positioning.

POSITIONING:
{positioning}

CONTENT PILLARS:
{pillars}

RELATED PROFESSIONAL TOPIC PATTERNS:
Derive these from the positioning, audience, content pillars, job title, and
story bank. Do not assume the user is a PM or PO unless their positioning says so.

TONE:
{tone}

CONFIDENTIALITY RULES:
{confidentiality}

EXISTING IDEAS:
{existing_ideas}

CONFIDENTIAL STORY BANK:
{stories}

Return a JSON array. Each item must have:
title, source, pillar, inspired_by_pattern, why_now, target_reader,
unique_user_angle, angle, evidence_to_use, do_not_mention.
Make every idea concrete, non-fluffy, and safe for public review."""


def render_idea(idea_id: str, item: dict) -> str:
    return f"""## {idea_id}: {item.get("title", "Untitled idea")}

Status: raw
Source: {item.get("source", "story_bank")}
Pillar: {item.get("pillar", "")}
Confidentiality: generalized
Public-safe: yes
Inspired by pattern: {item.get("inspired_by_pattern", "").strip()}
Why now: {item.get("why_now", "").strip()}
Target reader: {item.get("target_reader", "").strip()}
Unique user angle: {item.get("unique_user_angle", "").strip()}

Angle:
{item.get("angle", "").strip()}

Evidence to use:
{item.get("evidence_to_use", "").strip()}

Do not mention:
{item.get("do_not_mention", "").strip()}
"""


def generate(config_path: Path | None = None) -> list[str]:
    config = load_linkedin_config(config_path)
    if not linkedin_enabled(config):
        logger.info("[linkedin] Idea generation disabled.")
        return []

    ideas_path = configured_path(config, "ideas")
    existing = read_text(ideas_path)
    count = int(config.get("idea_generation", {}).get("ideas_per_run", 5))

    prompt = PROMPT.format(
        count=count,
        positioning=config.get("positioning", ""),
        pillars=format_yaml_list(config.get("content_pillars", [])),
        tone=format_yaml_list(config.get("tone", [])),
        confidentiality=format_yaml_list(config.get("confidentiality", {}).get("forbidden_public_details", [])),
        existing_ideas=existing[-4000:],
        stories=story_bank_text()[:12000],
    )

    payload = extract_json(complete_linkedin(SYSTEM, prompt))
    if not isinstance(payload, list):
        raise ValueError("Idea generation response must be a JSON array")

    next_id = next_idea_id(existing)
    current = int(next_id.split("-")[1])
    rendered = []
    for offset, item in enumerate(payload[:count]):
        if not isinstance(item, dict):
            continue
        rendered.append(render_idea(f"IDEA-{current + offset:04d}", item))

    if rendered:
        append_section(ideas_path, "\n\n".join(rendered))
    logger.info("[linkedin] Added %s idea(s) to %s", len(rendered), ideas_path)
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate public-safe LinkedIn raw ideas.")
    parser.add_argument("--config", type=Path, help="Optional standalone LinkedIn YAML config path")
    args = parser.parse_args()
    generate(args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
