"""Doctor and repository integrity checks."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

from job_hunter.agent_context import validate_score_file
from job_hunter.agent_context._utils import _read_yaml
from job_hunter.ux.applications import CANONICAL_STATUSES, load_applications


def _check(name: str, ok: bool, detail: str = "", fix: str = "") -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail, "fix": fix}


def doctor(root: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append(
        _check(
            "python_version",
            sys.version_info >= (3, 12),
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "Install Python 3.12 or newer.",
        )
    )
    checks.append(
        _check(
            "editable_package",
            _module_available("job_hunter"),
            "job_hunter package importable",
            "Run: pip install -e . from the job-hunter repo root.",
        )
    )
    checks.append(
        _check(
            "docker",
            shutil.which("docker") is not None,
            "Docker CLI",
            "Install/start Docker Desktop for local PDF compilation.",
        )
    )
    job_hunter_cfg = _read_yaml(root / "config" / "job_hunter.yml")
    resume_rel = _configured_profile_rel(job_hunter_cfg, "resume_tex", "profile/resume_double_column.tex")
    story_rel = _configured_profile_rel(job_hunter_cfg, "story_bank", "profile/story_bank.md")
    for rel in ("config/job_hunter.yml", resume_rel, story_rel):
        checks.append(_check(rel, (root / rel).exists(), rel, f"Create {rel}."))
    checks.extend(_schema_checks(root))
    checks.append(
        _check(
            "workflow_schedule",
            _workflow_schedule_configured(root),
            "find-jobs.yml schedule",
            "Uncomment schedule lines when ready for automatic scraping.",
        )
    )
    outputs = root / "outputs"
    try:
        outputs.mkdir(exist_ok=True)
        probe = outputs / ".doctor_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        writable = True
    except OSError:
        writable = False
    checks.append(_check("outputs_writable", writable, "outputs/", "Fix filesystem permissions."))
    onboarding = onboarding_status(root, checks)
    return {
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
        "onboardingNeeded": onboarding["onboardingNeeded"],
        "missing": onboarding["missing"],
        "warnings": onboarding["warnings"],
        "onboarding": onboarding,
    }


def _module_available(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _schema_checks(root: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for path in sorted((root / "config").glob("*.yml")):
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
            checks.append(_check(f"yaml:{path.name}", True, path.name))
        except Exception as exc:
            checks.append(_check(f"yaml:{path.name}", False, str(exc), f"Fix {path.name}."))
    return checks


def _configured_profile_rel(data: dict[str, Any], key: str, default: str) -> str:
    value = str((data.get("profile") or {}).get(key) or default)
    path = Path(value)
    return path.as_posix() if path.is_absolute() else value.replace("\\", "/")


def _workflow_schedule_configured(root: Path) -> bool:
    workflow = root / ".github" / "workflows" / "find-jobs.yml"
    if not workflow.exists():
        return False
    for line in workflow.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- cron:") and not line.lstrip().startswith("#"):
            return True
    return False


def onboarding_status(root: Path, checks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Return first-run setup state for agent onboarding."""
    missing: list[str] = []
    warnings: list[str] = []

    job_hunter_cfg = _read_yaml(root / "config" / "job_hunter.yml")
    if not (root / "config" / "job_hunter.yml").exists():
        missing.append("config/job_hunter.yml")
    elif not _has_enabled_region(job_hunter_cfg):
        missing.append("config/job_hunter.yml:regions")

    resume_rel = _configured_profile_rel(job_hunter_cfg, "resume_tex", "profile/resume_double_column.tex")
    resume_path = root / resume_rel
    if not resume_path.exists():
        missing.append(resume_rel)
    elif not _resume_filled(resume_path):
        missing.append(f"{resume_rel}:filled")

    career_rel = _configured_profile_rel(job_hunter_cfg, "career_context", "profile/career_context.md")
    career_path = root / career_rel
    if not career_path.exists():
        missing.append(career_rel)
    elif not _career_context_filled(career_path):
        missing.append(f"{career_rel}:filled")

    story_rel = _configured_profile_rel(job_hunter_cfg, "story_bank", "profile/story_bank.md")
    story_path = root / story_rel
    if not story_path.exists() or not _has_final_story(story_path):
        missing.append(f"{story_rel}:final_stories")

    if checks is None:
        workflow_configured = _workflow_schedule_configured(root)
        outputs_writable = _outputs_writable(root)
    else:
        workflow_configured = _check_ok(checks, "workflow_schedule")
        outputs_writable = _check_ok(checks, "outputs_writable")
    if not workflow_configured:
        warnings.append("workflow_schedule")
    if not outputs_writable:
        warnings.append("outputs_writable")

    return {
        "onboardingNeeded": bool(missing),
        "missing": missing,
        "warnings": warnings,
    }


def _check_ok(checks: list[dict[str, Any]], name: str) -> bool:
    for check in checks:
        if check.get("name") == name:
            return bool(check.get("ok"))
    return False


def _has_enabled_region(data: dict[str, Any]) -> bool:
    regions = data.get("regions")
    if not isinstance(regions, dict) or not regions:
        return False
    _placeholder = "your city"
    return any(
        isinstance(region, dict)
        and region.get("enabled", True)
        and str(region.get("location", "")).strip().lower() != _placeholder
        for region in regions.values()
    )


def _resume_filled(path: Path) -> bool:
    """Return True if the resume .tex has been personalised beyond template placeholders."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if re.search(r"\\name\s*\{\s*Name\s*\}", text):
        return False
    if re.search(r"\\scshape\s+Name\b", text):
        return False
    return True


def _career_context_filled(path: Path) -> bool:
    """Return True if career_context.md has content beyond empty template fields."""
    text = path.read_text(encoding="utf-8", errors="replace")
    filled = sum(1 for line in text.splitlines() if re.match(r"^-\s+[^:]+:\s+\S", line))
    return filled >= 3


def _has_final_story(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace")
    marker = "# Final"
    idx = text.lower().find(marker.lower())
    if idx == -1:
        return False
    final_text = text[idx:]
    meaningful = [
        line.strip()
        for line in final_text.splitlines()[1:]
        if line.strip()
        and not line.strip().startswith("<!--")
        and not line.strip().startswith("#")
        and not line.strip().startswith("---")
    ]
    return bool(meaningful)


def _outputs_writable(root: Path) -> bool:
    outputs = root / "outputs"
    try:
        outputs.mkdir(exist_ok=True)
        probe = outputs / ".doctor_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def verify_repository(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    apps = load_applications(root)["applications"]
    seen_keys: dict[str, str] = {}
    for app in apps:
        slug = str(app.get("slug") or "")
        status = str(app.get("status") or "")
        if status not in CANONICAL_STATUSES:
            errors.append(f"outputs/applications.yml: {slug or '<missing>'} invalid status {status}")
        if not slug:
            errors.append("outputs/applications.yml: application missing slug")
            continue
        job_dir = root / "outputs" / "jobs" / slug
        if not job_dir.exists():
            errors.append(f"outputs/applications.yml: missing job folder outputs/jobs/{slug}/")
            continue
        key = f"{str(app.get('company') or '').lower()}::{str(app.get('title') or '').lower()}"
        if key != "::" and key in seen_keys:
            warnings.append(f"possible duplicate applications: {seen_keys[key]} and {slug}")
        elif key != "::":
            seen_keys[key] = slug
        score_path = job_dir / "score.yml"
        if score_path.exists():
            validation = validate_score_file(score_path)
            if not validation["valid"]:
                errors.append(f"{score_path.as_posix()}: {validation['error']}")
        else:
            warnings.append(f"outputs/jobs/{slug}/score.yml missing")
        if not (job_dir / "evaluation.md").exists():
            warnings.append(f"outputs/jobs/{slug}/evaluation.md missing")
        if status == "tailored" and not (job_dir / "resume_tailored.tex").exists():
            errors.append(f"outputs/jobs/{slug}/resume_tailored.tex missing")
        elif status == "tailored" and not (job_dir / "resume_tailored.pdf").exists():
            warnings.append(f"outputs/jobs/{slug}/resume_tailored.pdf missing")

    errors.extend(_readme_link_errors(root))
    errors.extend(_processed_consistency_errors(root, apps))
    for rel in (
        "outputs/state/agent_candidate_batch.json",
        "outputs/state/agent_candidate_queue.json",
        "outputs/state/batch_scores.yml",
        "outputs/state/batch_screen.yml",
        "outputs/state/batch_judgment.yml",
    ):
        if (root / rel).exists():
            warnings.append(f"stale transient queue: {rel}")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _readme_link_errors(root: Path) -> list[str]:
    readme = root / "README.md"
    if not readme.exists():
        return []
    errors: list[str] = []
    text = readme.read_text(encoding="utf-8", errors="replace")
    import re

    for rel in re.findall(r"\[Files\]\((outputs/jobs/[^)]+/)\)", text):
        if not (root / rel).exists():
            errors.append(f"README.md: broken Files link {rel}")
    return errors


def _processed_consistency_errors(root: Path, apps: list[dict[str, Any]]) -> list[str]:
    state_path = root / "outputs" / "state" / "discovered_urls.yml"
    if not state_path.exists():
        return []
    try:
        state = yaml.safe_load(state_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return [f"{state_path.as_posix()}: invalid YAML: {exc}"]
    errors = []
    discovered = set(state.get("discovered") or [])
    for app in apps:
        url = str(app.get("url") or "")
        if url and app.get("status") in CANONICAL_STATUSES and url not in discovered:
            errors.append(f"discovered_urls.yml: missing discovered URL for {app.get('slug')}")
    return errors


def dump_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)
