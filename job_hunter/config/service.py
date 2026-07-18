"""Backend config service: safe read/validate/save/undo for user-editable config files.

Editable files (config/job_hunter.yml, profile/career_context.md)
are read and written as raw user content — never through get_job_hunter_config()'s merged
runtime defaults — so a save can never bake code-owned defaults into disk.

Every save is guarded by a SHA-256 revision token of the current file bytes (rejecting
stale saves), written through a same-directory temp file + fsync + os.replace, and backed
up to outputs/state/config_backups/ for one-level Undo.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from job_hunter.config.loader import get_job_hunter_config
from job_hunter.config.removed_keys import reject_removed_user_config

MAX_CAREER_CONTEXT_BYTES = 512 * 1024

JOB_HUNTER_CONFIG_REL = Path("config/job_hunter.yml")
CAREER_CONTEXT_REL = Path("profile/career_context.md")
STORY_BANK_REL = Path("profile/story_bank.md")

_BACKUP_DIR_REL = Path("outputs/state/config_backups")
_LOGICAL_FILES: dict[str, Path] = {
    "job_hunter_config": JOB_HUNTER_CONFIG_REL,
    "career_context": CAREER_CONTEXT_REL,
    "story_bank": STORY_BANK_REL,
}


def _career_context_rel(root: Path) -> Path:
    """The configured profile.career_context path — doctor/readiness honor it, so writers must too."""
    path = root / JOB_HUNTER_CONFIG_REL
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, yaml.YAMLError):
        data = {}
    value = str((data.get("profile") or {}).get("career_context") or "") if isinstance(data, dict) else ""
    return Path(value) if value else CAREER_CONTEXT_REL


def _resume_tex_rel(root: Path) -> Path:
    """The configured profile.resume_tex path — doctor/readiness honor it, so writers must too."""
    path = root / JOB_HUNTER_CONFIG_REL
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, yaml.YAMLError):
        data = {}
    value = str((data.get("profile") or {}).get("resume_tex") or "") if isinstance(data, dict) else ""
    return Path(value) if value else Path("profile/resume_double_column.tex")


def get_revision(path: Path) -> str:
    """SHA-256 hex digest of the file's current bytes (empty-file digest if missing)."""
    data = path.read_bytes() if path.exists() else b""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def validate_job_hunter_yaml(data: Any, root: Path) -> list[str]:
    """Structural validation for job_hunter.yml: removed keys, then JSON schema."""
    if not isinstance(data, dict):
        return ["config must be a YAML mapping"]

    errors: list[str] = []
    try:
        reject_removed_user_config(data)
    except ValueError as exc:
        errors.append(str(exc))

    from job_hunter.filters import FILTER_TYPES, canonicalize_filter_config, validate_filter_choices

    raw_filters = data.get("filters") or {}
    if isinstance(raw_filters, dict):
        unknown = sorted(set(raw_filters) - set(FILTER_TYPES) - {"languages"})
        if unknown:
            errors.append(f"Unknown filter type(s): {', '.join(unknown)}")
    canonical = canonicalize_filter_config(data)
    errors.extend(validate_filter_choices(data))
    schema_path = root / "config" / "schemas" / "job_hunter.schema.json"
    if schema_path.exists():
        try:
            import jsonschema

            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.validate(instance=canonical, schema=schema)
        except jsonschema.ValidationError as exc:
            errors.append(exc.message)
        except ImportError:
            pass
    return errors


def _normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}"


def validate_company_targets(targets: Any) -> list[str]:  # noqa: C901
    """Structural validation for job_hunter.yml's companies.targets list."""
    if not isinstance(targets, list):
        return ["companies.targets must be a list"]

    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for i, entry in enumerate(targets):
        if not isinstance(entry, dict):
            errors.append(f"companies.targets[{i}]: must be a mapping")
            continue
        name = str(entry.get("name") or "").strip()
        url = str(entry.get("url") or "").strip()
        country = str(entry.get("country") or "").strip().upper()
        if not name:
            errors.append(f"companies.targets[{i}]: 'name' is required")
        if not url:
            errors.append(f"companies.targets[{i}]: 'url' is required")
        elif urlsplit(url).scheme != "https":
            errors.append(f"companies.targets[{i}]: 'url' must be https ({url!r})")
        if len(country) != 2:
            errors.append(f"companies.targets[{i}]: 'country' must be an ISO alpha-2 code")
        if "enabled" in entry and not isinstance(entry.get("enabled"), bool):
            errors.append(f"companies.targets[{i}]: 'enabled' must be a boolean")

        if name and url and country:
            key = (_normalize_url(url), country)
            if key in seen:
                errors.append(f"companies.targets[{i}]: duplicate url+country")
            seen.add(key)
    return errors


def validate_career_context(text: str) -> list[str]:
    errors: list[str] = []
    if "\x00" in text:
        errors.append("career_context.md must not contain NUL bytes")
    if len(text.encode("utf-8")) > MAX_CAREER_CONTEXT_BYTES:
        errors.append(f"career_context.md exceeds max size of {MAX_CAREER_CONTEXT_BYTES} bytes")
    return errors


# ---------------------------------------------------------------------------
# Atomic write + backup
# ---------------------------------------------------------------------------


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(content)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def _backup_path(root: Path, logical_name: str) -> Path:
    return root / _BACKUP_DIR_REL / f"{logical_name}.bak"


def _safe_replace(
    root: Path, logical_name: str, rel_path: Path, new_bytes: bytes, expected_revision: str
) -> dict[str, Any]:
    """Write new_bytes to rel_path iff expected_revision matches the file's current revision.

    Backs up the previous bytes (one slot per logical file) before replacing so a
    subsequent undo_last_save() can restore them.
    """
    path = root / rel_path
    current_revision = get_revision(path)
    if expected_revision != current_revision:
        return {
            "ok": False,
            "errors": ["File changed on disk since it was loaded. Reload and try again."],
            "warnings": [],
            "revision": current_revision,
        }

    previous_bytes = path.read_bytes() if path.exists() else b""
    try:
        _atomic_write(_backup_path(root, logical_name), previous_bytes)
        _atomic_write(path, new_bytes)
    except OSError as exc:
        return {
            "ok": False,
            "errors": [f"Could not save {rel_path.as_posix()}: {exc}"],
            "warnings": [],
            "revision": current_revision,
        }
    return {"ok": True, "errors": [], "warnings": [], "revision": get_revision(path)}


# ---------------------------------------------------------------------------
# job_hunter.yml
# ---------------------------------------------------------------------------


def read_job_hunter_config(root: Path) -> dict[str, Any]:
    path = root / JOB_HUNTER_CONFIG_REL
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return {"ok": True, "data": text, "revision": get_revision(path), "errors": [], "warnings": []}


def save_job_hunter_config(root: Path, raw_yaml_text: str, expected_revision: str) -> dict[str, Any]:
    path = root / JOB_HUNTER_CONFIG_REL
    try:
        parsed = yaml.safe_load(raw_yaml_text) or {}
    except yaml.YAMLError as exc:
        return {"ok": False, "errors": [f"Invalid YAML: {exc}"], "warnings": [], "revision": get_revision(path)}

    errors = validate_job_hunter_yaml(parsed, root)
    if errors:
        return {"ok": False, "errors": errors, "warnings": [], "revision": get_revision(path)}

    result = _safe_replace(
        root, "job_hunter_config", JOB_HUNTER_CONFIG_REL, raw_yaml_text.encode("utf-8"), expected_revision
    )
    if result["ok"]:
        get_job_hunter_config.cache_clear()
    return result


_FORM_OPTIONAL_PROFILE_KEYS = ("latex_class", "profile_image")


def config_to_form(data: dict[str, Any]) -> dict[str, Any]:
    """Project the guided-editable subset of job_hunter.yml into a plain JSON-safe dict.

    Covers every top-level key the schema allows (mode/profile/job_titles/regions/
    filters/scoring) except llm, where only default_provider is guided-editable —
    providers/models/max_tokens/max_workers/rate_limits/ollama are advanced-only.
    """
    profile = data.get("profile") or {}
    from job_hunter.filters import canonicalize_filter_config

    filters = canonicalize_filter_config(data).get("filters") or {}
    scoring = data.get("scoring") or {}
    llm = data.get("llm") or {}
    return {
        "mode": data.get("mode", "agent"),
        "profile": {
            "resume_tex": profile.get("resume_tex", ""),
            "story_bank": profile.get("story_bank", ""),
            "career_context": profile.get("career_context", ""),
            "latex_class": profile.get("latex_class", ""),
            "profile_image": profile.get("profile_image", ""),
        },
        "job_titles": list(data.get("job_titles") or []),
        "regions": deepcopy(data.get("regions") or {}),
        "filters": deepcopy(filters),
        "scoring": {
            "min_fit_score": scoring.get("min_fit_score", 70),
            "max_years_experience_required": scoring.get("max_years_experience_required"),
            "batch_size": scoring.get("batch_size", 15),
            "strategic_overrides": deepcopy(scoring.get("strategic_overrides") or []),
        },
        "llm_default_provider": llm.get("default_provider", "anthropic"),
        "include_startups": bool((data.get("companies") or {}).get("include_startups", False)),
    }


def _apply_form_profile(profile: dict[str, Any], form_profile: dict[str, Any]) -> dict[str, Any]:
    profile = dict(profile)
    for key in ("resume_tex", "story_bank", "career_context"):
        if form_profile.get(key):
            profile[key] = form_profile[key]
    for key in _FORM_OPTIONAL_PROFILE_KEYS:
        if form_profile.get(key):
            profile[key] = form_profile[key]
        else:
            profile.pop(key, None)
    return profile


def _apply_form_scoring(scoring: dict[str, Any], form_scoring: dict[str, Any]) -> dict[str, Any]:
    scoring = dict(scoring)
    if form_scoring.get("min_fit_score") is not None:
        scoring["min_fit_score"] = form_scoring["min_fit_score"]
    if form_scoring.get("batch_size") is not None:
        scoring["batch_size"] = form_scoring["batch_size"]
    max_years = form_scoring.get("max_years_experience_required")
    if max_years in (None, ""):
        scoring.pop("max_years_experience_required", None)
    else:
        scoring["max_years_experience_required"] = max_years
    overrides = [o for o in (form_scoring.get("strategic_overrides") or []) if o.get("company")]
    if overrides:
        scoring["strategic_overrides"] = overrides
    else:
        scoring.pop("strategic_overrides", None)
    return scoring


def apply_form_to_config(data: dict[str, Any], form: dict[str, Any]) -> dict[str, Any]:
    """Return data with guided-editable fields replaced by form's values.

    Anything outside the guided form's coverage (llm.providers/models/max_tokens/
    max_workers/rate_limits/ollama, and any future schema keys) passes through
    untouched, so the Advanced YAML tab remains the only way to edit them.
    """
    merged = deepcopy(data)
    merged["mode"] = form.get("mode") or merged.get("mode", "agent")
    merged["profile"] = _apply_form_profile(merged.get("profile") or {}, form.get("profile") or {})
    merged["job_titles"] = [str(t).strip() for t in (form.get("job_titles") or []) if str(t).strip()]
    merged["regions"] = form.get("regions") or {}

    merged["filters"] = deepcopy(form.get("filters") or {})
    if not merged["filters"].get("hunt_languages"):
        merged["filters"]["hunt_languages"] = ["en"]
    if not merged["filters"].get("experience_levels"):
        from job_hunter.config.reference_data import experience_level_names

        merged["filters"]["experience_levels"] = experience_level_names()
    merged.pop("exclusions", None)
    merged.pop("career_stage", None)
    merged["scoring"] = _apply_form_scoring(merged.get("scoring") or {}, form.get("scoring") or {})

    companies = dict(merged.get("companies") or {})
    companies["include_startups"] = bool(form.get("include_startups", False))
    if companies.get("targets") or companies["include_startups"]:
        merged["companies"] = companies
    else:
        merged.pop("companies", None)

    llm = dict(merged.get("llm") or {})
    if form.get("llm_default_provider"):
        llm["default_provider"] = form["llm_default_provider"]
    merged["llm"] = llm

    return merged


def apply_onboarding_prefs(data: dict[str, Any], prefs: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
    """Apply the compact Get-Started search-setup fields onto existing job_hunter.yml data.

    Touches only mode, experience_levels, job_titles, the "primary" region, and
    excluded-industry filter — leaves scoring, llm, other regions, and other
    filter groups untouched.
    """
    merged = deepcopy(data)
    if prefs.get("mode"):
        merged["mode"] = prefs["mode"]
    merged["job_titles"] = [str(t).strip() for t in (prefs.get("job_titles") or []) if str(t).strip()]

    regions = dict(merged.get("regions") or {})
    primary = dict(regions.get("primary") or {})
    primary["enabled"] = True
    primary["primary"] = True
    location = prefs.get("location")
    if isinstance(location, dict):
        for key in ("country", "scope", "city_id"):
            if key in location:
                primary[key] = location[key]
        primary.pop("location", None)
    elif prefs.get("country") or location:
        from job_hunter.config.locations import location_to_config, resolve_config_location

        country = str(prefs.get("country") or "").strip().upper()
        primary.update(location_to_config(resolve_config_location(country, str(location or ""))))
        primary.pop("location", None)
    if prefs.get("search_lang"):
        primary["search_lang"] = str(prefs["search_lang"])
    regions["primary"] = primary
    merged["regions"] = regions

    industries = [str(i).strip() for i in (prefs.get("excluded_industries") or []) if str(i).strip()]
    filters = dict(merged.get("filters") or {})
    filters["excluded_industries"] = industries
    from job_hunter.config.reference_data import resolve_experience_group_ids
    from job_hunter.core.posting_types import STUDENT_POSTING_TYPES

    previous_levels = [str(v) for v in filters.get("experience_levels", []) or []]
    was_student = "student" in resolve_experience_group_ids(previous_levels)
    experience_levels = [str(v).strip() for v in (prefs.get("experience_levels") or []) if str(v).strip()]
    if experience_levels:
        filters["experience_levels"] = experience_levels
        is_student = "student" in resolve_experience_group_ids(experience_levels)
        scoring = dict(merged.get("scoring") or {})
        if is_student and not was_student:
            filters["posting_types"] = list(STUDENT_POSTING_TYPES)
            if scoring.get("min_fit_score", 70) == 70:
                scoring["min_fit_score"] = 60
        elif was_student and not is_student:
            filters.pop("posting_types", None)
            if scoring.get("min_fit_score") == 60:
                scoring["min_fit_score"] = 70
        merged["scoring"] = scoring
    hunt_languages = [str(v).strip() for v in (prefs.get("hunt_languages") or []) if str(v).strip()]
    if hunt_languages:
        filters["hunt_languages"] = hunt_languages
    merged["filters"] = filters

    if "include_startups" in prefs:
        companies = dict(merged.get("companies") or {})
        companies["include_startups"] = bool(prefs["include_startups"])
        merged["companies"] = companies

    return merged


# ---------------------------------------------------------------------------
# companies.targets (a section of job_hunter.yml — see job_hunter.companies for the
# package-owned catalog + runtime store; targets are the user's own additions)
# ---------------------------------------------------------------------------


def _normalize_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for entry in targets:
        item: dict[str, Any] = {
            "name": str(entry.get("name") or "").strip(),
            "url": str(entry.get("url") or "").strip(),
            "country": str(entry.get("country") or "").strip().upper(),
        }
        city = str(entry.get("city") or "").strip()
        if city:
            item["city"] = city
        industry = str(entry.get("industry") or "").strip()
        if industry:
            item["industry"] = industry
        company_type = str(entry.get("company_type") or "").strip()
        if company_type:
            item["company_type"] = company_type
        funding_stage = str(entry.get("funding_stage") or "").strip()
        if funding_stage:
            item["funding_stage"] = funding_stage
        if entry.get("enabled", True) is False:
            item["enabled"] = False
        normalized.append(item)
    return normalized


def read_company_targets(root: Path) -> dict[str, Any]:
    path = root / JOB_HUNTER_CONFIG_REL
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    targets = ((data or {}).get("companies") or {}).get("targets") or []
    return {"ok": True, "data": {"targets": targets}, "revision": get_revision(path), "errors": [], "warnings": []}


def save_company_targets(root: Path, targets: list[dict[str, Any]], expected_revision: str) -> dict[str, Any]:
    """Write companies.targets into job_hunter.yml — the one editable config file.

    Guarded by the whole file's revision, same as raw YAML edits: targets live in
    the same document, not a second file, so a stale save anywhere in job_hunter.yml
    is rejected here too.
    """
    path = root / JOB_HUNTER_CONFIG_REL
    errors = validate_company_targets(targets)
    if errors:
        return {"ok": False, "errors": errors, "warnings": [], "revision": get_revision(path)}

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    except yaml.YAMLError as exc:
        return {"ok": False, "errors": [f"Invalid YAML: {exc}"], "warnings": [], "revision": get_revision(path)}
    if not isinstance(data, dict):
        data = {}

    normalized = _normalize_targets(targets)
    if normalized:
        companies = dict(data.get("companies") or {})
        companies["targets"] = normalized
        data["companies"] = companies
    else:
        companies = dict(data.get("companies") or {})
        companies.pop("targets", None)
        if companies:
            data["companies"] = companies
        else:
            data.pop("companies", None)

    schema_errors = validate_job_hunter_yaml(data, root)
    if schema_errors:
        return {"ok": False, "errors": schema_errors, "warnings": [], "revision": get_revision(path)}

    new_text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    result = _safe_replace(
        root, "job_hunter_config", JOB_HUNTER_CONFIG_REL, new_text.encode("utf-8"), expected_revision
    )
    if result["ok"]:
        get_job_hunter_config.cache_clear()
    return result


# ---------------------------------------------------------------------------
# profile/career_context.md
# ---------------------------------------------------------------------------


def read_career_context(root: Path) -> dict[str, Any]:
    path = root / _career_context_rel(root)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return {"ok": True, "data": text, "revision": get_revision(path), "errors": [], "warnings": []}


def read_story_bank(root: Path) -> dict[str, Any]:
    path = root / STORY_BANK_REL
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return {"ok": True, "data": text, "revision": get_revision(path), "errors": [], "warnings": []}


def read_resume_tex(root: Path) -> dict[str, Any]:
    path = root / _resume_tex_rel(root)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return {"ok": True, "data": text, "revision": get_revision(path), "errors": [], "warnings": []}


def save_career_context(root: Path, text: str, expected_revision: str) -> dict[str, Any]:
    rel = _career_context_rel(root)
    errors = validate_career_context(text)
    if errors:
        return {"ok": False, "errors": errors, "warnings": [], "revision": get_revision(root / rel)}
    return _safe_replace(root, "career_context", rel, text.encode("utf-8"), expected_revision)


def _validate_profile_text(text: str, filename: str) -> list[str]:
    errors: list[str] = []
    if "\x00" in text:
        errors.append(f"{filename} must not contain NUL bytes")
    if len(text.encode("utf-8")) > MAX_CAREER_CONTEXT_BYTES:
        errors.append(f"{filename} exceeds max size of {MAX_CAREER_CONTEXT_BYTES} bytes")
    return errors


def save_story_bank(root: Path, text: str, expected_revision: str) -> dict[str, Any]:
    """Write a chatbot-authored story_bank.md replacement.

    Guards against a pasted reply silently populating '## Final' content that
    wasn't already in the file — final promotion stays a manual, human step for
    both the coding-agent and any-chatbot paths.
    """
    errors = _validate_profile_text(text, "story_bank.md")
    path = root / STORY_BANK_REL
    previous = path.read_text(encoding="utf-8") if path.exists() else ""
    new_final = _final_sections(text) - _final_sections(previous)
    if new_final:
        errors.append("New content appeared under a '## Final' heading — move it to Draft and promote it yourself.")
    if errors:
        return {"ok": False, "errors": errors, "warnings": [], "revision": get_revision(path)}
    return _safe_replace(root, "story_bank", STORY_BANK_REL, text.encode("utf-8"), expected_revision)


def _final_sections(text: str) -> set[str]:
    """Content under every '## Final' heading, one string per role block."""
    sections: set[str] = set()
    lines = text.splitlines()
    in_final = False
    current: list[str] = []
    for line in lines:
        if line.strip().startswith("## Final"):
            in_final = True
            current = []
            continue
        if line.strip().startswith("##") or line.strip().startswith("# "):
            if in_final and current:
                sections.add("\n".join(current).strip())
            in_final = False
            continue
        if in_final:
            current.append(line)
    if in_final and current:
        sections.add("\n".join(current).strip())
    return {s for s in sections if s}


def save_resume_tex(root: Path, text: str, expected_revision: str) -> dict[str, Any]:
    """Write a chatbot-authored resume .tex replacement to the configured profile.resume_tex path.

    Sanity check only (not a LaTeX parser): the original file's \\documentclass line
    must still be present, confirming the reply preserved the template structure
    rather than replacing it with unrelated content.
    """
    rel = _resume_tex_rel(root)
    path = root / rel
    errors = _validate_profile_text(text, path.name)
    previous = path.read_text(encoding="utf-8") if path.exists() else ""
    documentclass = next((line.strip() for line in previous.splitlines() if "\\documentclass" in line), None)
    if documentclass and documentclass not in text:
        errors.append(
            "Resume content must preserve the original \\documentclass line — the LaTeX structure looks changed."
        )
    if errors:
        return {"ok": False, "errors": errors, "warnings": [], "revision": get_revision(path)}
    return _safe_replace(root, "resume_tex", rel, text.encode("utf-8"), expected_revision)


def save_resume_style(root: Path, text: str, expected_revision: str) -> dict[str, Any]:
    """Write a preamble-only resume .tex change (dashboard Settings -> Resume Style form).

    Sanity check: the detected template type (AltaCV vs article) must be unchanged —
    looser than save_resume_tex's exact-documentclass-line check, since a style change
    legitimately edits that line's font-size/paper options.
    """
    from job_hunter.config.resume_style import detect_template

    rel = _resume_tex_rel(root)
    path = root / rel
    errors = _validate_profile_text(text, path.name)
    previous = path.read_text(encoding="utf-8") if path.exists() else ""
    if detect_template(previous) != detect_template(text):
        errors.append("Resume template type changed unexpectedly — refusing to save.")
    if errors:
        return {"ok": False, "errors": errors, "warnings": [], "revision": get_revision(path)}
    return _safe_replace(root, "resume_tex", rel, text.encode("utf-8"), expected_revision)


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------


_DYNAMIC_LOGICAL_FILES = {"career_context": _career_context_rel, "resume_tex": _resume_tex_rel}


def undo_last_save(root: Path, logical_name: str) -> dict[str, Any]:
    """Restore the one backup slot kept for logical_name. Consumes the backup (one-level)."""
    dynamic = _DYNAMIC_LOGICAL_FILES.get(logical_name)
    rel_path = dynamic(root) if dynamic else _LOGICAL_FILES.get(logical_name)
    if rel_path is None:
        return {"ok": False, "errors": [f"Unknown config file: {logical_name}"], "warnings": [], "revision": ""}

    backup = _backup_path(root, logical_name)
    if not backup.exists():
        return {"ok": False, "errors": ["No backup available to undo."], "warnings": [], "revision": ""}

    path = root / rel_path
    try:
        _atomic_write(path, backup.read_bytes())
    except OSError as exc:
        return {"ok": False, "errors": [f"Undo failed: {exc}"], "warnings": [], "revision": get_revision(path)}
    with suppress(OSError):
        backup.unlink()

    if logical_name == "job_hunter_config":
        get_job_hunter_config.cache_clear()
    return {"ok": True, "errors": [], "warnings": [], "revision": get_revision(path)}
