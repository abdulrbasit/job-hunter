"""Shared utility helpers for agent_context sub-modules."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from job_hunter.tracker import repo_path


def _root(root: Path | None = None) -> Path:
    return root if root is not None else repo_path()


def _read_json_or_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return yaml.safe_load(text) or {}


def _clip(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    suffix = " ... [truncated]"
    if limit <= len(suffix):
        return suffix[:limit]
    return text[: limit - len(suffix)].rstrip() + suffix


def _resolve_path(root: Path, path: Path | str) -> Path:
    resolved = Path(path)
    return resolved if resolved.is_absolute() else root / resolved


def _prefer_compiled(path: Path, root: Path) -> Path:
    """Return the compiled counterpart of a profile file if it exists."""
    compiled = root / "outputs" / "state" / "compiled" / (path.stem + ".min" + path.suffix)
    return compiled if compiled.exists() else path


def job_language_context(root: Path, job: str) -> dict[str, Any]:
    """Shared language block for every per-job context payload.

    Deterministic routing: persisted posting language (meta.json, re-detected from
    jd.md as a fallback for legacy folders) → output language gated by hunt_languages
    → which base resume serves it. `language_rules` is non-empty exactly when no base
    resume exists in the output language (translate-and-tailor)."""
    import json as _json

    from job_hunter.config.loader import get_config
    from job_hunter.config.resumes import normalized_resumes, resume_spec_for
    from job_hunter.filters import filter_values
    from job_hunter.writing.language import job_language, resolve_output_language, translation_rules

    job_dir = root / "outputs" / "jobs" / job
    meta: dict[str, Any] = {}
    meta_path = job_dir / "meta.json"
    if meta_path.exists():
        try:
            meta = _json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
    jd_path = job_dir / "jd.md"
    jd_text = jd_path.read_text(encoding="utf-8") if jd_path.exists() else ""
    job_lang = job_language(str(meta.get("language") or ""), str(meta.get("title") or ""), jd_text)

    config = get_config("job_hunter")
    profile = config.get("profile") or {}
    base_lang, _specs = normalized_resumes(profile)
    output = resolve_output_language(job_lang, filter_values(config, "hunt_languages"), base_lang)
    chosen, spec = resume_spec_for(profile, output)
    return {
        "job_language": job_lang,
        "output_language": output,
        "base_language": base_lang,
        "source_resume_language": chosen,
        "source_resume_tex": spec.get("resume_tex", ""),
        "language_rules": list(translation_rules(output)) if chosen != output else [],
    }
