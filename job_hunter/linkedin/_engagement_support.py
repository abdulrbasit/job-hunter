"""Support helpers for LinkedIn engagement discovery."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

from job_hunter.linkedin._config import read_text, repo_path, write_text


@dataclass
class Candidate:
    kind: str
    url: str
    title: str
    description: str
    source: str
    query: str = ""
    topic: str = ""
    relationship_type: str = ""
    score: int = 0
    reason: str = ""
    fingerprint: str = ""
    suggested_action: str = "review manually"
    message_variants: list[str] | None = None


def state_path(config: dict[str, Any], policy: dict[str, Any]) -> Path:
    value = Path(policy.get("state_file", "state.yml"))
    if value.is_absolute():
        return value
    config_dir = config.get("__config_dir")
    return Path(config_dir) / value if config_dir else repo_path(value)


def canonical_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, "", ""))


def stable_key(url: str, text: str = "") -> str:
    canonical = canonical_url(url)
    if canonical:
        return canonical
    return hashlib.sha1(text.lower().encode("utf-8")).hexdigest()  # noqa: S324


def fingerprint(*parts: str) -> str:
    text = " ".join(part for part in parts if part).lower()
    text = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha1(text.encode("utf-8")).hexdigest()  # noqa: S324


def topic_from_query(query: str) -> str:
    match = re.search(r'"([^"]+)"', query or "")
    return match.group(1) if match else "this topic"


def clean_title(title: str) -> str:
    title = re.sub(r"\s+-\s+LinkedIn\s*$", "", title or "", flags=re.IGNORECASE)
    title = re.sub(r"\s+\|\s+LinkedIn\s*$", "", title, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", title).strip() or "LinkedIn result"


def person_name(title: str) -> str:
    cleaned = clean_title(title)
    for separator in (" - ", " | ", " @ "):
        if separator in cleaned:
            return cleaned.split(separator, 1)[0].strip()
    return cleaned


def trim_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(".,;:") + "."


def clean_excerpt(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def candidate_text(candidate: Candidate) -> str:
    return f"{candidate.title} {candidate.description} {candidate.query} {candidate.topic}".lower()


def load_state(config: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    data = yaml.safe_load(read_text(state_path(config, policy), "{}")) or {}
    return {
        "seen_people": list(data.get("seen_people", [])),
        "skipped_urls": list(data.get("skipped_urls", [])),
        "message_fingerprints": list(data.get("message_fingerprints", [])),
    }


def save_state(config: dict[str, Any], policy: dict[str, Any], state: dict[str, Any]) -> None:
    normalized = {key: sorted(set(value)) for key, value in state.items()}
    write_text(state_path(config, policy), yaml.safe_dump(normalized, sort_keys=False, allow_unicode=False))


def render_people(items: list[Candidate]) -> str:
    if not items:
        return "_No people suggestions returned._"
    sections = []
    for item in items:
        messages = item.message_variants or []
        messages_text = "\n".join(f"  - {msg}" for msg in messages)
        sections.append(
            f"""### {person_name(item.title)}

- Role/context: {item.title}
- Link: {item.url}
- Score: {item.score}
- Why relevant: {item.reason}
- Evidence: {clean_excerpt(item.description)[:300]}
- Relationship type: {item.relationship_type}
- Suggested action: {item.suggested_action}
- Ask readiness: cold
- Message variants:
{messages_text}
"""
        )
    return "\n\n".join(sections)


def update_state(state: dict[str, Any], selected: dict[str, list[Candidate]]) -> dict[str, Any]:
    for candidate in selected["people"] + selected["recruiters"]:
        state.setdefault("seen_people", []).append(stable_key(candidate.url, candidate.fingerprint))
        state.setdefault("seen_people", []).append(candidate.fingerprint)
        for message in candidate.message_variants or []:
            state.setdefault("message_fingerprints", []).append(fingerprint(message))
    return state
