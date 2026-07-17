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
from job_hunter.core.utils import read_yaml
from job_hunter.sources.career_pages._rendering import is_chromium_installed
from job_hunter.sources.search import canonicalize_url
from job_hunter.tracking.applications import CANONICAL_STATUSES, load_applications


def _check(name: str, ok: bool, detail: str = "", fix: str = "") -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail, "fix": fix}


def legacy_owned_paths(root: Path) -> list[Path]:
    """Workspace-local location/filter files that must not exist — data is package-owned."""
    return [
        root / "config" / "locations",
        root / "config" / "location_data",
        root / "config" / "locations.yml",
        root / "config" / "locations.json",
        root / "config" / "filters",
        root / "config" / "filters.yml",
        root / "config" / "filters.json",
        root / "config" / "schemas" / "filter.schema.json",
    ]


def doctor(root: Path) -> dict[str, Any]:
    from job_hunter.config.migrations import migrate_career_pages, migrate_career_stage, migrate_legacy_exclusions

    migrate_legacy_exclusions(root)
    migrate_career_pages(root)
    migrate_career_stage(root)
    checks: list[dict[str, Any]] = []
    job_hunter_config = read_yaml(root / "config" / "job_hunter.yml")
    from job_hunter.config.locations import legacy_location_warnings

    location_warnings = legacy_location_warnings(job_hunter_config)
    forbidden_location_paths = [
        root / "config" / "locations",
        root / "config" / "location_data",
        root / "config" / "locations.yml",
        root / "config" / "locations.json",
    ]
    forbidden_filter_paths = [
        root / "config" / "filters",
        root / "config" / "filters.yml",
        root / "config" / "filters.json",
        root / "config" / "schemas" / "filter.schema.json",
    ]
    mode = str(job_hunter_config.get("mode") or "agent")
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
            "package_owned_locations",
            not any(path.exists() for path in forbidden_location_paths),
            "location catalogs load from job_hunter package resources",
            "Remove workspace location datasets; reinstall the package to restore bundled data.",
        )
    )
    checks.append(
        _check(
            "package_owned_filters",
            not any(path.exists() for path in forbidden_filter_paths),
            "filter definitions and taxonomies load from job_hunter package resources",
            "Run job-hunter update to fold obsolete filter files into config/job_hunter.yml.",
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
    docker_available = shutil.which("docker") is not None
    checks.append(
        _check(
            "docker",
            docker_available or mode == "agent",
            "Docker CLI" if docker_available else "Optional in agent mode; required for autonomous PDF compilation.",
            "Install/start Docker Desktop for llm-api PDF compilation.",
        )
    )
    if mode == "llm-api":
        provider = str((job_hunter_config.get("llm") or {}).get("default_provider") or "anthropic")
        module = {"anthropic": "anthropic", "openai": "openai", "google": "google", "ollama": "openai"}.get(provider)
        if module:
            checks.append(
                _check(
                    f"llm_provider:{provider}",
                    _module_available(module),
                    f"{provider} SDK",
                    "Reinstall job-hunter-kit to restore its bundled LLM provider SDKs.",
                )
            )
    resume_rel = _configured_profile_rel(job_hunter_config, "resume_tex", "profile/resume_double_column.tex")
    story_rel = _configured_profile_rel(job_hunter_config, "story_bank", "profile/story_bank.md")
    for rel in ("config/job_hunter.yml", resume_rel, story_rel):
        checks.append(_check(rel, (root / rel).exists(), rel, f"Create {rel}."))
    for skill_md in (".claude/skills/job-hunter/SKILL.md", ".agents/skills/job-hunter/SKILL.md"):
        checks.append(
            _check(skill_md, (root / skill_md).exists(), skill_md, "Run `job-hunter update` to reinstall skills.")
        )
    checks.extend(_schema_checks(root))
    checks.append(_config_schema_check(root))
    checks.append(_companies_store_check(root))
    checks.extend(_telemetry_checks(root))
    telemetry_warnings = _telemetry_warnings(root)
    schedule = _workflow_schedule_configured(root)
    checks.append(
        _check(
            "workflow_schedule",
            True,
            "configured" if schedule else "optional; manual runs remain available",
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
    checks.append(
        _check(
            "playwright_chromium",
            is_chromium_installed(),
            "chromium launchable",
            "Run: playwright install chromium",
        )
    )
    onboarding = onboarding_status(root, checks)
    return {
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
        "onboardingNeeded": onboarding["onboardingNeeded"],
        "missing": onboarding["missing"],
        "warnings": onboarding["warnings"] + location_warnings + telemetry_warnings,
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


def _config_schema_check(root: Path) -> dict[str, Any]:
    from job_hunter.config.service import validate_job_hunter_yaml

    config_path = root / "config" / "job_hunter.yml"
    if not config_path.exists():
        return _check("config_schema", False, "config/job_hunter.yml missing", "Run job-hunter init.")
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return _check("config_schema", False, str(exc), "Fix config/job_hunter.yml, then rerun job-hunter doctor.")
    errors = validate_job_hunter_yaml(data, root)
    if errors:
        return _check(
            "config_schema", False, "; ".join(errors), "Fix config/job_hunter.yml, then rerun job-hunter doctor."
        )
    return _check("config_schema", True, "config/job_hunter.yml matches schema")


def _companies_store_check(root: Path) -> dict[str, Any]:
    legacy = root / "config" / "career_pages.yml"
    if legacy.exists():
        return _check(
            "companies_store",
            False,
            "config/career_pages.yml still present after migration",
            "Run job-hunter doctor again, or check outputs/state/config_backups/career_pages.yml.bak.",
        )
    from job_hunter.companies import store

    store.ensure_seeded(root)
    count = store.company_count(root)
    unclassified_user = store.company_count(root, source="user", industry="other")
    detail = f"{count} companies in the runtime store"
    if unclassified_user:
        detail += f"; {unclassified_user} of your own targets need an industry assigned"
    return _check("companies_store", True, detail)


def _telemetry_checks(root: Path) -> list[dict[str, Any]]:
    """Verify agent-CLI hooks are wired for token telemetry (populates Analytics).

    job-hunter installs both hook files unconditionally regardless of which agent
    CLI the user actually runs, so hooks.json existing is not evidence Codex is in
    use — gate the machine-global OTel check on ~/.codex existing instead.
    """
    import os

    checks = [
        _hook_check(root, "telemetry_hooks_claude", root / ".claude" / "settings.json", "claude-code"),
        _hook_check(root, "telemetry_hooks_codex", root / ".codex" / "hooks.json", "codex"),
    ]
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    if codex_home.exists():
        checks.append(_codex_otel_check(codex_home))
    return checks


def _hook_check(root: Path, name: str, path: Path, backend: str) -> dict[str, Any]:
    fix = "Run `job-hunter update` to (re)install token telemetry hooks."
    rel = path.relative_to(root).as_posix()
    if not path.exists():
        return _check(name, False, f"{rel} missing", fix)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _check(name, False, f"{rel} is not valid JSON", fix)
    needle = f"job-hunter internal telemetry-hook --backend {backend} --event prompt"
    prompt_hooks = (data.get("hooks") or {}).get("UserPromptSubmit") or []
    wired = any(
        needle in str(hook.get("command", ""))
        for group in prompt_hooks
        if isinstance(group, dict)
        for hook in group.get("hooks", [])
        if isinstance(hook, dict)
    )
    if not wired:
        return _check(name, False, f"{rel} missing job-hunter's UserPromptSubmit hook", fix)
    return _check(name, True, f"{rel} wired for token telemetry")


def _codex_otel_check(codex_home: Path) -> dict[str, Any]:
    import tomllib

    config_path = codex_home / "config.toml"
    fix = "Run `job-hunter update` to add the [otel] export block to ~/.codex/config.toml."
    if not config_path.exists():
        return _check("telemetry_codex_otel", False, f"{config_path} missing", fix)
    try:
        parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return _check("telemetry_codex_otel", False, f"invalid TOML: {exc}", fix)
    endpoint = json.dumps(parsed.get("otel") or {})
    if "127.0.0.1:4318" not in endpoint:
        return _check(
            "telemetry_codex_otel",
            False,
            "~/.codex/config.toml [otel] does not export to the job-hunter collector (127.0.0.1:4318) — "
            "token usage from Codex sessions will never reach Analytics",
            fix,
        )
    return _check("telemetry_codex_otel", True, "~/.codex/config.toml exports OTel logs to the job-hunter collector")


def _telemetry_warnings(root: Path) -> list[str]:
    """Non-blocking telemetry pipeline warnings — collector/protocol/correlation health.

    Separate from `_telemetry_checks` (hook file wiring, hard pass/fail) because these
    require live collector/DB state and should never fail doctor outright.
    """
    from job_hunter.metrics.telemetry import telemetry_status

    warnings: list[str] = []
    status = telemetry_status(root)
    if not status["collector_healthy"]:
        warnings.append(
            "telemetry collector is not running or not reachable at 127.0.0.1:4318 — "
            "restart Claude Code/Codex or run a skill to relaunch it"
        )
    if status["last_rejected_content_type"]:
        warnings.append(
            f"telemetry collector rejected a payload with Content-Type "
            f"'{status['last_rejected_content_type']}' — only http/json OTLP is supported; "
            "set OTEL_EXPORTER_OTLP_PROTOCOL=http/json"
        )
    protocol = _claude_otlp_protocol(root)
    if protocol and protocol != "http/json":
        warnings.append(
            f"'.claude/settings.json' sets OTEL_EXPORTER_OTLP_PROTOCOL={protocol} — "
            "the local collector only understands http/json; run `job-hunter update` to fix it"
        )
    if status["hooks_wired_but_no_otel_events"]:
        warnings.append(
            "telemetry hooks are wired and a run was recorded, but no OTel token events "
            "have arrived — run `job-hunter internal telemetry-status --json` for details"
        )
    if status.get("hooks_invoked_but_no_runs_ever"):
        warnings.append(
            "telemetry hooks are wired and firing, but zero runs have ever been recorded — "
            "the hook process may be failing before it can write to metrics.db; run "
            "`job-hunter internal telemetry-hook --backend claude-code --event prompt` "
            "manually from this workspace to see the error"
        )
    return warnings


def _claude_otlp_protocol(root: Path) -> str:
    path = root / ".claude" / "settings.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""
    return str((data.get("env") or {}).get("OTEL_EXPORTER_OTLP_PROTOCOL") or "")


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

    job_hunter_config = read_yaml(root / "config" / "job_hunter.yml")
    if not (root / "config" / "job_hunter.yml").exists():
        missing.append("config/job_hunter.yml")
    elif not _has_enabled_region(job_hunter_config):
        missing.append("config/job_hunter.yml:regions")

    resume_rel = _configured_profile_rel(job_hunter_config, "resume_tex", "profile/resume_double_column.tex")
    resume_path = root / resume_rel
    if not resume_path.exists():
        missing.append(resume_rel)
    elif not _resume_filled(resume_path):
        missing.append(f"{resume_rel}:filled")

    career_rel = _configured_profile_rel(job_hunter_config, "career_context", "profile/career_context.md")
    career_path = root / career_rel
    if not career_path.exists():
        missing.append(career_rel)
    elif not _career_context_filled(career_path):
        missing.append(f"{career_rel}:filled")

    story_rel = _configured_profile_rel(job_hunter_config, "story_bank", "profile/story_bank.md")
    story_path = root / story_rel
    if not story_path.exists() or not _has_final_story(story_path):
        missing.append(f"{story_rel}:final_stories")

    workflow_configured = _workflow_schedule_configured(root)
    outputs_writable = _outputs_writable(root) if checks is None else _check_ok(checks, "outputs_writable")
    if not workflow_configured:
        warnings.append("workflow_schedule")
    if not outputs_writable:
        warnings.append("outputs_writable")

    return {
        "onboardingNeeded": bool(missing),
        "missing": missing,
        "warnings": warnings,
    }


def onboarding_checklist(root: Path) -> dict[str, Any]:
    """Human-readable, actionable checklist derived from onboarding_status() — no new detection logic."""
    status = onboarding_status(root)
    missing = set(status["missing"])
    warnings = set(status["warnings"])

    job_hunter_config = read_yaml(root / "config" / "job_hunter.yml")
    resume_rel = _configured_profile_rel(job_hunter_config, "resume_tex", "profile/resume_double_column.tex")
    career_rel = _configured_profile_rel(job_hunter_config, "career_context", "profile/career_context.md")
    story_rel = _configured_profile_rel(job_hunter_config, "story_bank", "profile/story_bank.md")

    items = [
        {
            "id": "regions",
            "label": "Add at least one enabled region with a real city",
            "done": "config/job_hunter.yml" not in missing and "config/job_hunter.yml:regions" not in missing,
            "action_hint": "Settings → Guided → Regions",
        },
        {
            "id": "resume",
            "label": "Personalize your resume beyond the template placeholders",
            "done": resume_rel not in missing and f"{resume_rel}:filled" not in missing,
            "action_hint": f"Edit {resume_rel}, then rerun doctor",
        },
        {
            "id": "career_context",
            "label": "Fill in your career context (targeting, resume style, tone)",
            "done": career_rel not in missing and f"{career_rel}:filled" not in missing,
            "action_hint": "Get Started → Career Profile panel, or Settings → Career Context",
        },
        {
            "id": "story_bank",
            "label": "Write at least one Final STAR story",
            "done": f"{story_rel}:final_stories" not in missing,
            "action_hint": f"Add a ### entry under Final in {story_rel}",
        },
        {
            "id": "api_key",
            "label": "Configure an API key for your LLM provider",
            "done": _api_key_configured(job_hunter_config),
            "action_hint": "Get Started → API Key",
        },
        {
            "id": "workflow_schedule",
            "label": "Enable the GitHub Actions schedule for unattended hunting",
            "done": "workflow_schedule" not in warnings,
            "action_hint": "Get Started → GitHub Actions",
        },
        {
            "id": "outputs_writable",
            "label": "Make outputs/ writable",
            "done": "outputs_writable" not in warnings,
            "action_hint": "Fix filesystem permissions on outputs/",
        },
    ]
    done_count = sum(1 for item in items if item["done"])
    return {"items": items, "done_count": done_count, "total_count": len(items)}


def _api_key_configured(job_hunter_config: dict[str, Any]) -> bool:
    """A configured API key is required only in llm-api mode; agent mode uses Claude Code's own auth."""
    mode = str(job_hunter_config.get("mode") or "agent")
    if mode != "llm-api":
        return True
    from job_hunter.config.secrets import get_secret
    from job_hunter.llm.providers import PROVIDER_SECRET_ENV_VARS

    provider = str((job_hunter_config.get("llm") or {}).get("default_provider") or "anthropic")
    if provider == "ollama":
        return True
    env_var = PROVIDER_SECRET_ENV_VARS.get(provider, "")
    return bool(env_var and get_secret(env_var, required=False))


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


def _career_context_template_lines() -> frozenset[str]:
    from job_hunter.workspace.assets import workspace_assets_root

    text = workspace_assets_root().joinpath("profile/career_context.md").read_text(encoding="utf-8")
    return frozenset(line.strip() for line in text.splitlines() if line.strip())


def _career_context_filled(path: Path) -> bool:
    """Return True if career_context.md has meaningful content beyond the bundled template.

    Counts characters on lines that don't appear in the pristine template, so any
    format counts — prose, indented bullets, bold labels, chatbot imports.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    template_lines = _career_context_template_lines()
    novel = sum(
        len(stripped) for line in text.splitlines() if (stripped := line.strip()) and stripped not in template_lines
    )
    return novel >= 100


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
    db = root / "outputs" / "state" / "jobs.db"
    if not db.exists():
        return []
    from job_hunter.tracking.repository import get_all_known_urls

    known = get_all_known_urls(root)
    errors = []
    for app in apps:
        url = str(app.get("url") or "")
        if url and app.get("status") in CANONICAL_STATUSES and canonicalize_url(url) not in known:
            errors.append(f"jobs.db: missing URL for {app.get('slug')}")
    return errors


def dump_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)
