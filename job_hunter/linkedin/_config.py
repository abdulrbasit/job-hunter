"""Shared helpers for the LinkedIn content workflow."""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from job_hunter.config.defaults import LINKEDIN_DEFAULTS, deep_merge
from job_hunter.config.loader import ROOT, get_config, profile_path
from job_hunter.core.llm_utils import get_llm_role_settings
from job_hunter.llm.client import get_client as get_llm_client

logger = logging.getLogger(__name__)


def load_linkedin_config(path: Path | None = None) -> dict[str, Any]:
    if path is None:
        data = get_config("job_hunter")
        config = deep_merge(LINKEDIN_DEFAULTS, data.get("linkedin", {}) or {})
        config["__config_dir"] = str(ROOT / "outputs" / "linkedin")
        _apply_career_context(config)
        return config

    config_path = path.resolve()
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config = deep_merge(LINKEDIN_DEFAULTS, data.get("linkedin", data))
    config["__config_dir"] = str(config_path.parent)
    _apply_career_context(config)
    return config


def _apply_career_context(config: dict[str, Any]) -> None:
    try:
        career_context = profile_path("career_context", "profile/career_context.md").read_text(encoding="utf-8")
    except OSError:
        career_context = ""
    config["career_context"] = career_context
    if career_context and not str(config.get("positioning") or "").strip():
        config["positioning"] = career_context[:4000]


def linkedin_enabled(config: dict[str, Any]) -> bool:
    return bool(config.get("enabled", True))


def repo_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def configured_path(config: dict[str, Any], key: str) -> Path:
    value = config.get("files", {}).get(key)
    if not value:
        raise KeyError(f"Missing job_hunter.yml linkedin.files.{key}")
    return repo_path(value)


def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8")


def append_section(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = read_text(path)
    separator = "\n\n" if existing.strip() else ""
    path.write_text(existing.rstrip() + separator + text.strip() + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def story_bank_text() -> str:
    return profile_path("story_bank", "story_bank.md").read_text(encoding="utf-8")


def linkedin_model_settings() -> tuple[str, int]:
    settings = get_llm_role_settings("linkedin")
    return settings.model, settings.max_tokens


def complete_linkedin(system: str, user: str) -> str:
    model, max_tokens = linkedin_model_settings()
    return get_llm_client("linkedin").complete(
        system=system,
        user=user,
        model=model,
        max_tokens=max_tokens,
    )


def extract_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(1))


def strip_fenced_blocks(text: str) -> str:
    """Remove fenced examples before parsing markdown records."""
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def next_idea_id(ideas_text: str) -> str:
    ids = [int(n) for n in re.findall(r"IDEA-(\d{4})", strip_fenced_blocks(ideas_text))]
    return f"IDEA-{(max(ids) + 1) if ids else 1:04d}"


def format_yaml_list(values: list[str]) -> str:
    return "\n".join(f"- {value}" for value in values)


def today_slug() -> str:
    return date.today().isoformat()


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"\s+", "-", text.strip())
    return text[:60].strip("-") or "linkedin-draft"


def idea_blocks(ideas_text: str) -> list[dict[str, str]]:
    ideas_text = strip_fenced_blocks(ideas_text)
    matches = list(re.finditer(r"^## (IDEA-\d{4}): (.+)$", ideas_text, re.MULTILINE))
    blocks: list[dict[str, str]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(ideas_text)
        block = ideas_text[start:end].strip()
        blocks.append({"id": match.group(1), "title": match.group(2), "text": block})
    return blocks


def unconverted_ideas(ideas_text: str, source_status: str) -> list[dict[str, str]]:
    selected = []
    status_line = f"Status: {source_status}".lower()
    for block in idea_blocks(ideas_text):
        lower = block["text"].lower()
        if status_line in lower and "converted to draft: yes" not in lower:
            selected.append(block)
    return selected


def mark_ideas_converted(ideas_text: str, idea_ids: list[str], draft_paths: list[Path]) -> str:
    updated = ideas_text
    for idea_id, draft_path in zip(idea_ids, draft_paths, strict=False):
        pattern = re.compile(
            rf"(## {re.escape(idea_id)}: .+?)(?=\n## IDEA-\d{{4}}: |\Z)",
            re.DOTALL,
        )

        def replace(match: re.Match[str], _draft_path=draft_path) -> str:
            block = match.group(1).rstrip()
            try:
                rel = _draft_path.relative_to(ROOT).as_posix()
            except ValueError:
                rel = _draft_path.as_posix()
            if "Converted to draft:" in block:
                block = re.sub(r"Converted to draft:.*", "Converted to draft: yes", block)
            else:
                block += "\nConverted to draft: yes"
            if "Draft:" in block:
                block = re.sub(r"Draft:.*", f"Draft: {rel}", block)
            else:
                block += f"\nDraft: {rel}"
            return block + "\n"

        updated = pattern.sub(replace, updated, count=1)
    return updated
