"""Create weekly LinkedIn draft posts from unconverted raw ideas."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from job_hunter.config.loader import ROOT, setup_logging
from job_hunter.linkedin._config import (
    complete_linkedin,
    configured_path,
    extract_json,
    format_yaml_list,
    linkedin_enabled,
    load_linkedin_config,
    mark_ideas_converted,
    read_text,
    repo_path,
    slugify,
    today_slug,
    unconverted_ideas,
    write_text,
)

logger = setup_logging(log_level=os.environ.get("LOG_LEVEL", "INFO"))

SYSTEM = """You write LinkedIn draft posts for the configured professional profile.
Return JSON only. Do not include markdown fences."""

PROMPT = """Create {count} LinkedIn post drafts from these raw ideas.

Every draft must be public-safe and confidentiality-reviewed by design.
Do not mention forbidden details. Do not imply the user will post automatically.
No hype, no cliches, no generic thought leadership.

POSITIONING:
{positioning}

AUDIENCE:
{audience}

TONE:
{tone}

FORBIDDEN PHRASES:
{forbidden_phrases}

CONFIDENTIALITY FORBIDDEN DETAILS:
{confidentiality}

MAX WORDS PER POST:
{max_words}

RAW IDEAS:
{ideas}

Return a JSON array. Each item must have:
idea_id, title, pillar, post_text, confidentiality_notes, review_checklist."""


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def draft(config_path: Path | None = None) -> list[Path]:
    config = load_linkedin_config(config_path)
    if not linkedin_enabled(config):
        logger.info("[linkedin] Draft generation disabled.")
        return []

    ideas_path = configured_path(config, "ideas")
    ideas_text = read_text(ideas_path)

    draft_cfg = config.get("draft_generation", {})
    count = int(draft_cfg.get("posts_per_run", 2))
    source_status = str(draft_cfg.get("source_status", "raw"))
    selected = unconverted_ideas(ideas_text, source_status)[:count]
    if not selected:
        logger.info("[linkedin] No unconverted ideas found.")
        return []

    prompt = PROMPT.format(
        count=len(selected),
        positioning=config.get("positioning", ""),
        audience=format_yaml_list(config.get("audience", [])),
        tone=format_yaml_list(config.get("tone", [])),
        forbidden_phrases=format_yaml_list(config.get("forbidden_phrases", [])),
        confidentiality=format_yaml_list(config.get("confidentiality", {}).get("forbidden_public_details", [])),
        max_words=int(draft_cfg.get("max_words_per_post", 180)),
        ideas="\n\n".join(item["text"] for item in selected),
    )

    payload = extract_json(complete_linkedin(SYSTEM, prompt))
    if not isinstance(payload, list):
        raise ValueError("Draft generation response must be a JSON array")

    drafts_dir = repo_path(config.get("files", {}).get("drafts_dir", "linkedin/drafts"))
    drafts_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    for idx, item in enumerate(payload[: len(selected)], 1):
        if not isinstance(item, dict):
            continue
        idea_id = str(item.get("idea_id") or selected[idx - 1]["id"])
        title = str(item.get("title") or selected[idx - 1]["title"])
        path = drafts_dir / f"{today_slug()}_{idx:02d}_{slugify(title)}.md"
        text = f"""---
status: draft
source_ideas:
  - {idea_id}
pillar: {item.get("pillar", "")}
confidentiality_review: required
public_safe: pending
linkedin_write_actions: false
---

# {title}

{str(item.get("post_text", "")).strip()}

## Confidentiality Notes

{str(item.get("confidentiality_notes", "")).strip()}

## Review Checklist

{str(item.get("review_checklist", "")).strip()}
"""
        write_text(path, text)
        created.append(path)

    if created and draft_cfg.get("mark_converted", True):
        converted_ids = [
            str(item.get("idea_id") or selected[i]["id"]) for i, item in enumerate(payload[: len(created)])
        ]
        updated = mark_ideas_converted(ideas_text, converted_ids, created)
        write_text(ideas_path, updated)

    logger.info(
        "[linkedin] Created %s draft(s): %s",
        len(created),
        ", ".join(_display_path(p) for p in created),
    )
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Draft LinkedIn posts from raw ideas.")
    parser.add_argument("--config", type=Path, help="Optional standalone LinkedIn YAML config path")
    args = parser.parse_args()
    draft(args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
