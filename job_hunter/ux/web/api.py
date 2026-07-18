"""Python JS API exposed to the pywebview dashboard via window.pywebview.api.*"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ARTIFACTS = (
    ("resume", "Resume PDF", "resume_tailored.pdf", "pdf"),
    ("cover_letter", "Cover Letter", "cover_letter.md", "text"),
    ("evaluation", "Evaluation", "evaluation.md", "text"),
    ("research", "Company Research", "company_research.md", "text"),
    ("outreach", "Outreach Drafts", "outreach_drafts.md", "text"),
    ("interview", "Interview Prep", "interview_prep.md", "text"),
)
_ARTIFACT_MAP = {key: (filename, kind) for key, _label, filename, kind in ARTIFACTS}


def _open_path(path: Path) -> None:
    # Paths are resolved beneath outputs/jobs before reaching this OS boundary.
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])  # noqa: S603, S607
    elif sys.platform.startswith("linux"):
        subprocess.Popen(["xdg-open", str(path)])  # noqa: S603, S607
    else:
        raise OSError("Unsupported operating system.")


def _open_url(url: str) -> None:
    # Caller must already have checked the URL is http/https and known-configured.
    if sys.platform == "win32":
        os.startfile(url)  # type: ignore[attr-defined]  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", url])  # noqa: S603, S607
    elif sys.platform.startswith("linux"):
        subprocess.Popen(["xdg-open", url])  # noqa: S603, S607
    else:
        raise OSError("Unsupported operating system.")


def _copy_to_clipboard(text: str) -> None:
    """Write text to the OS clipboard from Python — never returned across the JS bridge.

    Secrets copied this way (API keys) are always plain ASCII, so a simple UTF-8
    encode is sufficient — no need to special-case Windows' console codepage.
    """
    data = text.encode("utf-8")
    if sys.platform == "win32":
        subprocess.run(["clip"], input=data, check=True)  # noqa: S603, S607
    elif sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=data, check=True)  # noqa: S603, S607
    elif sys.platform.startswith("linux"):
        subprocess.run(["xclip", "-selection", "clipboard"], input=data, check=True)  # noqa: S603, S607
    else:
        raise OSError("Unsupported operating system.")


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(microsecond=0).isoformat()


class DashAPI:
    def __init__(self, root: Path) -> None:
        self._root = root
        # Shared by start_hunt() and run_company_hunt() so a normal hunt and a
        # company hunt can never run concurrently against the same workspace.
        self._hunt_lock = threading.Lock()
        self._hunt_running = False
        self._hunt_started_at: str | None = None
        self._last_hunt_result: dict[str, Any] | None = None
        self._last_sync_result: dict[str, Any] | None = None
        self._last_finalize_result: dict[str, Any] | None = None
        self._chromium_lock = threading.Lock()
        self._chromium_running = False
        self._last_chromium_result: dict[str, Any] | None = None

    @staticmethod
    def _mutation_error(message: str, next_action: str) -> dict[str, Any]:
        return {"ok": False, "error": message, "next_action": next_action}

    def start_hunt(self) -> dict[str, Any]:
        """Typed run service for the normal (title/region) hunt — config controls
        mode/regions; no routine options. Shares the company-hunt lock so the two
        can never run concurrently against the same workspace."""
        with self._hunt_lock:
            if self._hunt_running:
                return {"ok": False, "status": "running", "error": "A hunt is already running."}
            self._hunt_running = True
            self._hunt_started_at = _now_iso()
        self._last_hunt_result = None
        threading.Thread(target=self._run_hunt_worker, daemon=True).start()
        return {"ok": True, "status": "running", "started_at": self._hunt_started_at}

    def _run_hunt_worker(self) -> None:
        import logging

        from job_hunter.config import get_mode
        from job_hunter.models import HuntInput
        from job_hunter.pipeline.hunt import run as run_hunt

        try:
            mode = get_mode()
            output = run_hunt(HuntInput(region_key="all", mode=mode))
            candidates = output.stats.total_after_policy
            tailored = len(output.jobs) if mode == "llm-api" else 0
            self._last_hunt_result = {
                "status": "succeeded",
                "finished_at": _now_iso(),
                "message": f"Fetched {output.stats.total_fetched}, {candidates} candidates, {tailored} tailored.",
                "fetched": output.stats.total_fetched,
                "candidates": candidates,
                "tailored": tailored,
                "next_action": "Continue in Claude/Codex" if mode == "agent" else "Review Applications",
            }
        except Exception:  # noqa: BLE001 — a crashed worker must not wedge _hunt_running or leak internals to the UI
            logging.getLogger(__name__).exception("[hunt] worker crashed")
            self._last_hunt_result = {
                "status": "failed",
                "finished_at": _now_iso(),
                "message": "The hunt failed. Check local logs for details.",
                "fetched": 0,
                "candidates": 0,
                "tailored": 0,
                "next_action": "Check Settings → Diagnostics, then try again.",
            }
        finally:
            with self._hunt_lock:
                self._hunt_running = False

    def get_hunt_status(self) -> dict[str, Any]:
        with self._hunt_lock:
            running = self._hunt_running
            started_at = self._hunt_started_at
        if running:
            return {"ok": True, "status": "running", "started_at": started_at}
        if self._last_hunt_result is None:
            return {"ok": True, "status": "idle"}
        return {"ok": True, **self._last_hunt_result}

    def start_sync(self) -> dict[str, Any]:
        """Commit dirty state, merge the remote jobs.db, and push — no git commands for the
        user to run. Shares the hunt lock: sync replaces outputs/state/jobs.db on disk, which
        must never race a concurrent hunt or company-hunt write to the same file."""
        with self._hunt_lock:
            if self._hunt_running:
                return {"ok": False, "status": "running", "error": "A hunt or sync is already running."}
            self._hunt_running = True
        self._last_sync_result = None
        threading.Thread(target=self._run_sync_worker, daemon=True).start()
        return {"ok": True, "status": "running"}

    def _run_sync_worker(self) -> None:
        import logging

        from job_hunter.workspace.git_sync import sync_workspace

        try:
            result = sync_workspace(self._root)
            self._last_sync_result = {**result, "status": "succeeded" if result["ok"] else "failed"}
        except Exception:  # noqa: BLE001 — a crashed worker must not wedge _hunt_running
            logging.getLogger(__name__).exception("[sync] worker crashed")
            self._last_sync_result = {
                "ok": False,
                "status": "failed",
                "error": "Sync failed. Check local logs for details.",
            }
        finally:
            with self._hunt_lock:
                self._hunt_running = False

    def get_sync_status(self) -> dict[str, Any]:
        with self._hunt_lock:
            running = self._hunt_running
        if running:
            return {"ok": True, "status": "running"}
        if self._last_sync_result is None:
            return {"ok": True, "status": "idle"}
        return {"ok": True, **self._last_sync_result}

    def start_finalize(self, push: bool = False) -> dict[str, Any]:
        """Validate, commit, and optionally push durable run artifacts — the dashboard
        twin of `job-hunter finalize`. Shares the hunt lock for the same reason start_sync
        does: it can also merge/push outputs/state/jobs.db."""
        with self._hunt_lock:
            if self._hunt_running:
                return {"ok": False, "status": "running", "error": "A hunt or sync is already running."}
            self._hunt_running = True
        self._last_finalize_result = None
        threading.Thread(target=self._run_finalize_worker, args=(push,), daemon=True).start()
        return {"ok": True, "status": "running"}

    def _run_finalize_worker(self, push: bool) -> None:
        import logging

        from job_hunter.agent_context import validate_score_file
        from job_hunter.ux.health import verify_repository
        from job_hunter.workspace.finalize import run_finalize_core

        try:
            verify_errors = verify_repository(self._root)["errors"]
            result = run_finalize_core(
                self._root,
                verify_errors=verify_errors,
                validate_score_file=validate_score_file,
                push=push,
                mode="manual",
            )
            self._last_finalize_result = {**result, "status": "succeeded" if result["ok"] else "failed"}
        except Exception:  # noqa: BLE001 — a crashed worker must not wedge _hunt_running
            logging.getLogger(__name__).exception("[finalize] worker crashed")
            self._last_finalize_result = {
                "ok": False,
                "status": "failed",
                "error": "Finalize failed. Check local logs for details.",
            }
        finally:
            with self._hunt_lock:
                self._hunt_running = False

    def get_finalize_status(self) -> dict[str, Any]:
        with self._hunt_lock:
            running = self._hunt_running
        if running:
            return {"ok": True, "status": "running"}
        if self._last_finalize_result is None:
            return {"ok": True, "status": "idle"}
        return {"ok": True, **self._last_finalize_result}

    def start_company_hunt(self, mode: str = "new_changed") -> dict[str, Any]:
        """Spec-named alias for run_company_hunt (kept for the existing wired UI)."""
        return self.run_company_hunt(mode)

    def get_company_hunt_status(self) -> dict[str, Any]:
        """Spec-named alias for get_company_hunt_summary (kept for the existing wired UI)."""
        return self.get_company_hunt_summary()

    def get_onboarding(self) -> dict[str, Any]:
        from job_hunter.ux.health import doctor

        try:
            payload = doctor(self._root)
        except Exception:  # noqa: BLE001
            return {
                "ok": False,
                "onboardingNeeded": False,
                "missing_count": 0,
                "error": "Setup status is unavailable.",
                "next_action": "Run `job-hunter doctor` in the workspace.",
            }
        onboarding = payload["onboarding"]
        return {
            "ok": True,
            "onboardingNeeded": onboarding["onboardingNeeded"],
            "missing_count": len(onboarding["missing"]),
            "warning_count": len(onboarding["warnings"]),
        }

    def get_onboarding_checklist(self) -> dict[str, Any]:
        from job_hunter.ux.health import onboarding_checklist

        try:
            checklist = onboarding_checklist(self._root)
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": "Setup checklist is unavailable.", "next_action": "Run `job-hunter doctor`."}
        return {"ok": True, **checklist}

    def get_bootstrap(self) -> dict[str, Any]:
        """Everything the Get Started page needs on load: readiness, checklist, config revision."""
        from job_hunter.config import service
        from job_hunter.ux.health import onboarding_checklist
        from job_hunter.ux.web.readiness import get_readiness

        try:
            config_result = service.read_job_hunter_config(self._root)
            readiness = get_readiness(self._root)
            checklist = onboarding_checklist(self._root)
        except Exception:  # noqa: BLE001
            return {"ok": False, "data": None, "errors": ["Setup status is unavailable."], "warnings": []}
        return {
            "ok": True,
            "data": {
                "config_revision": config_result["revision"],
                "readiness": readiness,
                "checklist": checklist,
            },
            "errors": [],
            "warnings": [],
        }

    def save_onboarding_preferences(self, prefs: dict[str, Any], revision: str) -> dict[str, Any]:
        """Save the compact Get Started search-setup page (mode/experience_levels/titles/region/industries)."""
        import yaml

        from job_hunter.config import service

        raw = service.read_job_hunter_config(self._root)
        try:
            parsed = yaml.safe_load(raw["data"]) or {}
        except yaml.YAMLError as exc:
            return {"ok": False, "data": None, "errors": [f"Invalid YAML on disk: {exc}"], "warnings": []}
        merged = service.apply_onboarding_prefs(parsed if isinstance(parsed, dict) else {}, prefs)
        new_text = yaml.safe_dump(merged, sort_keys=False, allow_unicode=True)
        result = service.save_job_hunter_config(self._root, new_text, revision)
        return self._config_result(result)

    def _checklist_item_done(self, item_id: str) -> bool:
        from job_hunter.ux.health import onboarding_checklist

        items = onboarding_checklist(self._root)["items"]
        return any(item["id"] == item_id and item["done"] for item in items)

    def get_career_context_prompt(self) -> dict[str, Any]:
        """A copyable any-chatbot prompt for building career_context.md."""
        from job_hunter.config import service
        from job_hunter.config.onboarding_bundle import build_career_context_prompt

        current = service.read_career_context(self._root)["data"]
        prompt = build_career_context_prompt(current)
        return {"ok": True, "data": {"prompt": prompt}, "errors": [], "warnings": []}

    def import_career_context_prompt_reply(self, text: str) -> dict[str, Any]:
        """Parse a pasted any-chatbot reply and write it as the new career_context.md."""
        from job_hunter.config import service
        from job_hunter.config.onboarding_bundle import parse_single_section

        content, errors = parse_single_section(text, "CAREER_CONTEXT")
        if errors or content is None:
            return {"ok": False, "data": None, "errors": errors, "warnings": []}
        revision = service.read_career_context(self._root)["revision"]
        result = service.save_career_context(self._root, content, revision)
        if not result["ok"]:
            return {"ok": False, "data": None, "errors": result["errors"], "warnings": result["warnings"]}
        return {"ok": True, "data": None, "errors": [], "warnings": []}

    def get_story_bank_prompt(self) -> dict[str, Any]:
        """A copyable any-chatbot prompt for building story_bank.md."""
        from job_hunter.config import service
        from job_hunter.config.onboarding_bundle import build_story_bank_prompt

        current = service.read_story_bank(self._root)["data"]
        prompt = build_story_bank_prompt(current)
        return {"ok": True, "data": {"prompt": prompt}, "errors": [], "warnings": []}

    def import_story_bank_prompt_reply(self, text: str) -> dict[str, Any]:
        """Parse a pasted any-chatbot reply and write it as the new story_bank.md."""
        from job_hunter.config import service
        from job_hunter.config.onboarding_bundle import parse_single_section

        content, errors = parse_single_section(text, "STORY_BANK")
        if errors or content is None:
            return {"ok": False, "data": None, "errors": errors, "warnings": []}
        revision = service.read_story_bank(self._root)["revision"]
        result = service.save_story_bank(self._root, content, revision)
        if not result["ok"]:
            return {"ok": False, "data": None, "errors": result["errors"], "warnings": result["warnings"]}
        return {"ok": True, "data": None, "errors": [], "warnings": []}

    def get_resume_prompt(self) -> dict[str, Any]:
        """A copyable any-chatbot prompt for building the base resume .tex.

        Only available once career context and story bank are both filled — the
        prompt has nothing meaningful to embed otherwise.
        """
        from job_hunter.config import service
        from job_hunter.config.onboarding_bundle import build_resume_prompt

        if not (self._checklist_item_done("career_context") and self._checklist_item_done("story_bank")):
            return {
                "ok": False,
                "data": None,
                "errors": ["Fill in career context and story bank first — the resume prompt is built from them."],
                "warnings": [],
            }
        resume_tex = service.read_resume_tex(self._root)["data"]
        career_context = service.read_career_context(self._root)["data"]
        story_bank = service.read_story_bank(self._root)["data"]
        prompt = build_resume_prompt(resume_tex, career_context, story_bank)
        return {"ok": True, "data": {"prompt": prompt}, "errors": [], "warnings": []}

    def import_resume_prompt_reply(self, text: str) -> dict[str, Any]:
        """Parse a pasted any-chatbot reply and write it as the base resume .tex."""
        from job_hunter.config import service
        from job_hunter.config.onboarding_bundle import parse_single_section

        content, errors = parse_single_section(text, "BASE_RESUME")
        if errors or content is None:
            return {"ok": False, "data": None, "errors": errors, "warnings": []}
        revision = service.read_resume_tex(self._root)["revision"]
        result = service.save_resume_tex(self._root, content, revision)
        if not result["ok"]:
            return {"ok": False, "data": None, "errors": result["errors"], "warnings": result["warnings"]}
        return {"ok": True, "data": None, "errors": [], "warnings": []}

    def get_job_title_suggestions(self, query: str = "") -> dict[str, Any]:
        from job_hunter.core.job_titles import load_job_titles

        needle = query.strip().lower()
        titles = load_job_titles()
        matches = [t for t in titles if needle in t.lower()] if needle else titles
        return {"ok": True, "data": {"titles": matches[:20]}, "errors": [], "warnings": []}

    def remove_legacy_location_or_filter_files(self) -> dict[str, Any]:
        """One-click fix for the doctor package_owned_locations/package_owned_filters checks."""
        from job_hunter.ux.health import legacy_owned_paths

        removed = []
        for path in legacy_owned_paths(self._root):
            if not path.exists():
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append(str(path.relative_to(self._root)))
        return {"ok": True, "data": {"removed": removed}, "errors": [], "warnings": []}

    def start_chromium_install(self) -> dict[str, Any]:
        """One-click fix for the doctor playwright_chromium check; browser downloads are slow,
        so this runs on a background thread like start_hunt()."""
        with self._chromium_lock:
            if self._chromium_running:
                return {"ok": False, "status": "running", "error": "Chromium install is already running."}
            self._chromium_running = True
        self._last_chromium_result = None
        threading.Thread(target=self._run_chromium_install_worker, daemon=True).start()
        return {"ok": True, "status": "running"}

    def _run_chromium_install_worker(self) -> None:
        import logging

        try:
            proc = subprocess.run(  # noqa: S603
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode == 0:
                self._last_chromium_result = {"status": "succeeded", "message": "Chromium installed."}
            else:
                self._last_chromium_result = {
                    "status": "failed",
                    "message": proc.stderr.strip()[-500:] or "playwright install chromium failed.",
                }
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception("[chromium] install worker crashed")
            self._last_chromium_result = {"status": "failed", "message": "Chromium install failed unexpectedly."}
        finally:
            with self._chromium_lock:
                self._chromium_running = False

    def get_chromium_install_status(self) -> dict[str, Any]:
        with self._chromium_lock:
            running = self._chromium_running
        if running:
            return {"ok": True, "status": "running"}
        if self._last_chromium_result is None:
            return {"ok": True, "status": "idle"}
        return {"ok": True, **self._last_chromium_result}

    def run_update(self) -> dict[str, Any]:
        """Dashboard equivalent of `job-hunter update --yes` — refreshes bundled skills,
        workflows, and config schema without the CLI's git-dirty-check prompt, since the
        dashboard's own confirmation dialog already gates this call."""
        from job_hunter.config.migrations import migrate_legacy_exclusions, migrate_workspace_filter_files
        from job_hunter.workspace.assets import update_workspace_assets
        from job_hunter.workspace.operations import install_telemetry
        from job_hunter.workspace.operations import update_skills as run_update_skills
        from job_hunter.workspace.operations import update_workflows as run_update_workflows

        migrate_legacy_exclusions(self._root)
        migrate_workspace_filter_files(self._root)
        written = update_workspace_assets(self._root)
        skills_result = run_update_skills(self._root)
        workflows_result = run_update_workflows(self._root)
        telemetry_warnings = install_telemetry(self._root)
        return {
            "ok": True,
            "data": {
                "assets": len(written),
                "skills": len(skills_result.written),
                "workflows": len(workflows_result.written),
                "telemetry_warnings": telemetry_warnings,
            },
            "errors": [],
            "warnings": [],
        }

    def get_api_key_status(self) -> dict[str, Any]:
        from job_hunter.config.secrets import get_secret
        from job_hunter.core.utils import read_yaml
        from job_hunter.llm.providers import PROVIDER_SECRET_ENV_VARS

        config = read_yaml(self._root / "config" / "job_hunter.yml")
        provider = str((config.get("llm") or {}).get("default_provider") or "anthropic")
        if provider == "ollama":
            return {"ok": True, "provider": provider, "required": False, "configured": True}
        env_var = PROVIDER_SECRET_ENV_VARS.get(provider, "")
        configured = bool(env_var and get_secret(env_var, required=False))
        return {"ok": True, "provider": provider, "env_var": env_var, "required": True, "configured": configured}

    def save_api_key(self, value: str) -> dict[str, Any]:
        from job_hunter.core.utils import read_yaml
        from job_hunter.llm.providers import PROVIDER_SECRET_ENV_VARS

        value = value.strip()
        if not value:
            return self._mutation_error("API key cannot be empty.", "Paste a real key and try again.")
        config = read_yaml(self._root / "config" / "job_hunter.yml")
        provider = str((config.get("llm") or {}).get("default_provider") or "anthropic")
        env_var = PROVIDER_SECRET_ENV_VARS.get(provider, "")
        if not env_var:
            return self._mutation_error(
                f"No API key needed for provider '{provider}'.", "Change llm.default_provider if this is wrong."
            )
        try:
            import keyring

            keyring.set_password("job-hunter", env_var, value)
        except Exception as exc:  # noqa: BLE001
            return self._mutation_error(
                f"Could not store the key in the OS keyring: {exc}",
                "Install with: pip install 'job-hunter-kit[secrets]', or set the env var manually.",
            )
        return {"ok": True, "provider": provider, "env_var": env_var}

    _OPTIONAL_ACTIONS_SECRETS = (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ADZUNA_APP_ID",
        "ADZUNA_API_KEY",
        "REED_API_KEY",
    )

    def get_github_actions_guide(self) -> dict[str, Any]:
        """Guided (not automated) GitHub Actions setup info: the one required secret's
        name/configured status (never its value — see copy_github_actions_secret()),
        other optional secret names, the exact cron diff, and current schedule state.
        Never calls `gh` or pushes anything — the user still acts in GitHub's UI."""
        from job_hunter.config.secrets import get_secret
        from job_hunter.core.utils import read_yaml
        from job_hunter.llm.providers import PROVIDER_SECRET_ENV_VARS
        from job_hunter.ux.health import _workflow_schedule_configured

        config = read_yaml(self._root / "config" / "job_hunter.yml")
        provider = str((config.get("llm") or {}).get("default_provider") or "anthropic")
        required_env_var = PROVIDER_SECRET_ENV_VARS.get(provider, "")
        required_value = get_secret(required_env_var, required=False) if required_env_var else ""
        optional_names = [name for name in self._OPTIONAL_ACTIONS_SECRETS if name != required_env_var]
        return {
            "ok": True,
            "schedule_enabled": _workflow_schedule_configured(self._root),
            "required_secret": {
                "name": required_env_var,
                "configured": bool(required_value),
            },
            "optional_secret_names": optional_names,
            "yaml_diff": (
                "Uncomment in .github/workflows/find-jobs.yml:\n"
                "  schedule:\n"
                '    - cron: "0 18 * * 0-4"   # 20:00 Berlin (CEST) / 19:00 CET - Mon-Fri'
            ),
        }

    def copy_github_actions_secret(self) -> dict[str, Any]:
        """Copy the required LLM API secret straight to the OS clipboard.

        The value never crosses the JS bridge (unlike the old get_github_actions_guide
        payload) — Python reads the secret and writes it directly to the clipboard.
        """
        from job_hunter.config.secrets import get_secret
        from job_hunter.core.utils import read_yaml
        from job_hunter.llm.providers import PROVIDER_SECRET_ENV_VARS

        config = read_yaml(self._root / "config" / "job_hunter.yml")
        provider = str((config.get("llm") or {}).get("default_provider") or "anthropic")
        env_var = PROVIDER_SECRET_ENV_VARS.get(provider, "")
        value = get_secret(env_var, required=False) if env_var else ""
        if not value:
            return {"ok": False, "error": "No API key is configured."}
        try:
            _copy_to_clipboard(value)
        except (OSError, subprocess.SubprocessError):
            return {"ok": False, "error": "Could not access the system clipboard."}
        return {"ok": True}

    def get_seen_milestones(self) -> dict[str, Any]:
        path = self._root / "outputs" / "state" / "milestones.json"
        if not path.exists():
            return {"ok": True, "seen": []}
        try:
            seen = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"ok": True, "seen": []}
        return {"ok": True, "seen": seen if isinstance(seen, list) else []}

    def mark_milestone_seen(self, milestone_id: str) -> dict[str, Any]:
        path = self._root / "outputs" / "state" / "milestones.json"
        seen = set(self.get_seen_milestones()["seen"])
        seen.add(milestone_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sorted(seen)), encoding="utf-8")
        return {"ok": True, "seen": sorted(seen)}

    def get_application_streak(self) -> dict[str, Any]:
        from job_hunter.tracking.repository import get_application_streak

        try:
            streak = get_application_streak(self._root)
        except Exception:  # noqa: BLE001
            return {"ok": False, "current_streak": 0, "longest_streak": 0, "active_days": 0}
        return {"ok": True, **streak}

    def get_applications(
        self,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        status: str = "",
        sort: str = "date",
        direction: str = "desc",
    ) -> dict[str, Any]:
        from job_hunter.tracking.applications import CANONICAL_STATUSES, normalize_status
        from job_hunter.tracking.repository import get_jobs_page

        statuses = (normalize_status(status),) if status else CANONICAL_STATUSES
        applications, total = get_jobs_page(
            self._root,
            statuses=statuses,
            page=page,
            page_size=page_size,
            search=search,
            sort=sort,
            direction=direction,
            require_identity=True,
        )
        for app in applications:
            slug_date = str(app.get("slug") or "")[:10]
            app["date"] = (
                app.get("date")
                or (slug_date if len(slug_date) == 10 and slug_date[4:5] == "-" and slug_date[7:8] == "-" else "")
                or str(app.get("discovered_at") or app.get("created_at") or "")[:10]
            )
        size = min(200, max(1, int(page_size)))
        return {
            "items": applications,
            "total": total,
            "page": max(1, int(page)),
            "page_size": size,
            "pages": max(1, (total + size - 1) // size),
        }

    def _job_dir(self, slug: str) -> Path | None:
        jobs_root = (self._root / "outputs" / "jobs").resolve()
        job_dir = (jobs_root / slug).resolve()
        if not job_dir.is_relative_to(jobs_root) or job_dir.parent != jobs_root:
            return None
        return job_dir

    def _artifacts(self, slug: str) -> list[dict[str, Any]]:
        job_dir = self._job_dir(slug)
        return [
            {
                "key": key,
                "label": label,
                "filename": filename,
                "kind": kind,
                "available": bool(job_dir and (job_dir / filename).is_file()),
            }
            for key, label, filename, kind in ARTIFACTS
        ]

    def get_job_detail(self, slug: str) -> dict[str, Any]:
        from job_hunter.tracking.repository import get_job_by_slug

        record = get_job_by_slug(self._root, slug) or {}
        if record:
            return {
                "slug": slug,
                "meta": {
                    "title": record.get("title"),
                    "company": record.get("company"),
                    "location": record.get("location"),
                    "url": record.get("url"),
                    "region": record.get("region"),
                    "job_description_fetch_status": record.get("job_description_fetch_status"),
                },
                "score": {
                    "score": record.get("score"),
                    "decision": record.get("decision"),
                    "matched": record.get("matched_keywords") or [],
                    "gaps": record.get("gaps") or [],
                    "score_rationale": record.get("score_rationale"),
                    "recommendation": record.get("recommendation"),
                },
                "jd": (record.get("jd_text") or "")[:4000],
                "notes": record.get("notes") or [],
                "artifacts": self._artifacts(slug),
            }

        # Fallback: job folder exists on disk but hasn't been synced to jobs.db yet
        job_dir = self._job_dir(slug)
        if job_dir is None:
            return {"slug": slug, "meta": {}, "score": {}, "jd": "", "artifacts": self._artifacts(slug)}
        meta: dict[str, Any] = {}
        score: dict[str, Any] = {}
        jd_text = ""

        meta_path = job_dir / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))

        score_path = job_dir / "score.yml"
        if score_path.exists():
            import yaml

            score = yaml.safe_load(score_path.read_text(encoding="utf-8")) or {}

        jd_path = job_dir / "jd.md"
        if jd_path.exists():
            jd_text = jd_path.read_text(encoding="utf-8")[:4000]

        return {"slug": slug, "meta": meta, "score": score, "jd": jd_text, "artifacts": self._artifacts(slug)}

    def _artifact_path(self, slug: str, key: str) -> Path | None:
        job_dir = self._job_dir(slug)
        artifact = _ARTIFACT_MAP.get(key)
        if job_dir is None or artifact is None:
            return None
        path = (job_dir / artifact[0]).resolve()
        return path if path.parent == job_dir else None

    def get_artifact(self, slug: str, key: str) -> dict[str, Any]:
        path = self._artifact_path(slug, key)
        if path is None:
            return {"ok": False, "error": "Invalid artifact request."}
        if not path.is_file():
            return {"ok": False, "error": "Artifact not available."}
        filename, kind = _ARTIFACT_MAP[key]
        try:
            content = (
                base64.b64encode(path.read_bytes()).decode("ascii")
                if kind == "pdf"
                else path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError):
            return {"ok": False, "error": "Artifact could not be read."}
        return {"ok": True, "key": key, "kind": kind, "filename": filename, "content": content}

    def open_artifact(self, slug: str, key: str) -> dict[str, Any]:
        path = self._artifact_path(slug, key)
        if path is None:
            return {"ok": False, "error": "Invalid artifact request."}
        if not path.is_file():
            return {"ok": False, "error": "Artifact not available."}
        return self._launch(path)

    def open_job_folder(self, slug: str) -> dict[str, Any]:
        job_dir = self._job_dir(slug)
        if job_dir is None:
            return {"ok": False, "error": "Invalid job request."}
        if not job_dir.is_dir():
            return {"ok": False, "error": "Job folder not available."}
        return self._launch(job_dir)

    @staticmethod
    def _launch(path: Path) -> dict[str, Any]:
        try:
            _open_path(path.resolve())
        except OSError:
            return {"ok": False, "error": "Could not open path."}
        return {"ok": True}

    def _refresh_readme(self) -> None:
        from datetime import date

        from job_hunter.pipeline.stages.readme import update_readme_from_applications
        from job_hunter.tracking.applications import load_applications

        apps = load_applications(self._root)["applications"]
        update_readme_from_applications(apps, self._root, date.today().isoformat())

    def update_status(self, slug: str, status: str, note: str = "") -> dict[str, Any]:
        from job_hunter.tracking.applications import update_application_status

        try:
            result = dict(update_application_status(slug, status, root=self._root, note=note))
        except (ValueError, KeyError):
            return self._mutation_error(
                "Status could not be updated.",
                "Reload Applications and retry with a listed status.",
            )
        self._refresh_readme()
        return result

    def delete_application(self, slug: str) -> dict[str, Any]:
        from job_hunter.tracking.applications import delete_application

        try:
            delete_application(slug, self._root)
        except Exception:  # noqa: BLE001
            return self._mutation_error(
                "Application could not be deleted.",
                "Reload Applications and retry.",
            )
        self._refresh_readme()
        return {"ok": True, "error": ""}

    def delete_applications_batch(self, slugs: list[str]) -> dict[str, Any]:
        """One backend call for N application deletes — README refreshes once, not per slug."""
        from job_hunter.tracking.applications import delete_applications_batch

        try:
            result = delete_applications_batch([str(slug) for slug in slugs], root=self._root)
        except Exception:  # noqa: BLE001
            return {
                **self._mutation_error(
                    "Applications could not be deleted.",
                    "Reload Applications and retry the selected batch.",
                ),
                "deleted": 0,
                "skipped": [],
                "warnings": [],
            }
        self._refresh_readme()
        return {
            "ok": True,
            "error": "",
            "deleted": result["deleted"],
            "skipped": result["skipped"],
            "warnings": result["warnings"],
        }

    def get_unprocessed(
        self,
        scope: str = "active",
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        posting_type: str = "",
        company_type: str = "",
        sort: str = "date",
        direction: str = "desc",
    ) -> dict[str, Any]:
        from job_hunter.tracking.repository import display_status, get_jobs_page

        status_groups = {
            "active": ("candidate", "discovered"),
            "discarded": ("discarded", "processed"),
        }
        selected_statuses = status_groups.get(scope, status_groups["active"])
        rows, total = get_jobs_page(
            self._root,
            statuses=selected_statuses,
            page=page,
            page_size=page_size,
            search=search,
            posting_type=posting_type,
            company_type=company_type,
            sort=sort,
            direction=direction,
            require_identity=True,
        )
        items = [
            {
                "id": job.get("id"),
                "company": job.get("company"),
                "title": job.get("title"),
                "location": job.get("location"),
                "posting_type": job.get("posting_type"),
                "company_type": job.get("company_type"),
                "funding_stage": job.get("funding_stage"),
                "experience_unknown": bool(job.get("experience_unknown")),
                "source": job.get("source"),
                "source_url": job.get("source_url"),
                "status": display_status(str(job.get("status") or "")),
                "url": job.get("url"),
                "date": str(job.get("discovered_at") or job.get("created_at") or "")[:10],
            }
            for job in rows
        ]
        counts = {
            name: get_jobs_page(
                self._root,
                statuses=statuses,
                page=1,
                page_size=1,
                require_identity=True,
            )[1]
            for name, statuses in status_groups.items()
        }
        counts["total"] = counts["active"] + counts["discarded"]
        size = min(200, max(1, int(page_size)))
        return {
            "items": items,
            "total": total,
            "page": max(1, int(page)),
            "page_size": size,
            "pages": max(1, (total + size - 1) // size),
            "scope": scope if scope in status_groups else "active",
            "counts": counts,
        }

    def discard_unprocessed(self, job_id: int) -> dict[str, Any]:
        """Move one candidate to status='discarded' (never touches applications)."""
        from job_hunter.tracking.repository import set_status_by_id

        try:
            set_status_by_id(self._root, int(job_id), "discarded")
        except Exception:  # noqa: BLE001
            return self._mutation_error(
                "Candidate could not be discarded.",
                "Reload Candidates and retry.",
            )
        return {"ok": True, "error": ""}

    def discard_unprocessed_batch(self, job_ids: list[int]) -> dict[str, Any]:
        """One backend call for N candidate discards — replaces per-id Promise.all fan-out."""
        from job_hunter.tracking.repository import discard_job_ids

        try:
            result = discard_job_ids(self._root, [int(job_id) for job_id in job_ids])
        except Exception:  # noqa: BLE001
            return {
                **self._mutation_error(
                    "Candidates could not be discarded.",
                    "Reload Candidates and retry the selected batch.",
                ),
                "discarded": 0,
                "skipped": [],
            }
        return {"ok": True, "error": "", "discarded": result["discarded"], "skipped": result["skipped"]}

    def delete_unprocessed(self, job_id: int) -> dict[str, Any]:
        from job_hunter.tracking.repository import delete_job_by_id

        try:
            delete_job_by_id(self._root, int(job_id))
        except Exception:  # noqa: BLE001
            return self._mutation_error(
                "Candidate could not be deleted.",
                "Reload Candidates and retry.",
            )
        return {"ok": True, "error": ""}

    def run_company_hunt(self, mode: str = "new_changed") -> dict[str, Any]:
        """Kick off the company career-page browser hunt in the background.

        Progress is read back from the persisted company_hunt_runs/tasks tables (see
        get_company_hunt_summary / get_company_hunt_updates) instead of an in-memory
        dict — polling no longer means snapshotting a per-company list that grows to
        thousands of entries over a long run.
        """
        allowed = {"new_changed", "failed_only", "force_all", "resume"}
        if mode not in allowed:
            return self._mutation_error(
                "Unknown company-hunt mode.",
                "Choose a mode from the Company Hunt menu.",
            )
        with self._hunt_lock:
            if self._hunt_running:
                return {"already_running": True}
            self._hunt_running = True
        self._hunt_thread = threading.Thread(target=self._run_company_hunt_worker, args=(mode,), daemon=True)
        self._hunt_thread.start()
        return {"started": True}

    def _run_company_hunt_worker(self, mode: str) -> None:
        import logging

        from job_hunter.pipeline import browser_hunt

        try:
            browser_hunt.run(mode=mode)
        except Exception:  # noqa: BLE001 — a crashed worker must not wedge _hunt_running
            logging.getLogger(__name__).exception("[company-hunt] worker crashed")
        finally:
            with self._hunt_lock:
                self._hunt_running = False

    @staticmethod
    def _hunt_message(run: dict[str, Any]) -> str:
        if run["status"] == "error":
            return str(run.get("error") or "Something went wrong while checking company career pages.")
        total = int(run.get("total") or 0)
        skipped = int(run.get("skipped") or 0)
        failed = int(run.get("failed") or 0)
        inserted = int(run.get("jobs_inserted") or 0)
        checked = total - skipped
        candidates = "candidate" if inserted == 1 else "candidates"
        skip_note = f", {skipped} skipped (recently checked)" if skipped else ""
        if not failed:
            return f"{checked} of {total} companies checked{skip_note}. {inserted} new {candidates} found."
        ok = checked - failed
        return f"{ok} of {checked} companies checked ({failed} couldn't be reached){skip_note}. {inserted} new {candidates} found."

    def get_company_hunt_summary(self) -> dict[str, Any]:
        """Persisted run summary — one row, cheap to poll every few seconds even with
        2,000 companies (replaces the old in-memory per-company list snapshot)."""
        from job_hunter.tracking import company_hunts

        run = company_hunts.get_latest_run(self._root)
        with self._hunt_lock:
            running = self._hunt_running
        if run is None:
            return {"ok": True, "run": None, "running": running, "message": ""}
        message = "" if run["status"] == "running" else self._hunt_message(run)
        return {"ok": True, "run": run, "running": running, "message": message}

    def get_company_hunt_updates(self, run_id: int, after_id: int = 0) -> dict[str, Any]:
        """Incremental task rows for run_id since after_id — the UI appends these
        instead of re-fetching and re-rendering the whole task list every poll."""
        from job_hunter.tracking import company_hunts

        tasks = company_hunts.get_updates_since(self._root, int(run_id), int(after_id))
        cursor = tasks[-1]["update_id"] if tasks else int(after_id)
        return {"ok": True, "tasks": tasks, "cursor": cursor}

    def get_insights(self) -> dict[str, Any]:
        from collections import defaultdict

        from job_hunter.tracking.applications import filtered_applications
        from job_hunter.ux.analytics import analyze_pipeline

        report = analyze_pipeline(self._root)
        weekly: dict[str, int] = defaultdict(int)
        for app in filtered_applications(root=self._root):
            date_str = str(app.get("discovered_at") or app.get("created_at") or "")[:10]
            if date_str:
                from datetime import date as _date

                try:
                    d = _date.fromisoformat(date_str)
                    week_key = f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
                    weekly[week_key] += 1
                except ValueError:
                    pass

        report["weekly"] = dict(sorted(weekly.items())[-12:])
        return report

    def _config_mode(self) -> str:
        import yaml

        config_path = self._root / "config" / "job_hunter.yml"
        if not config_path.exists():
            return "agent"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return str(data.get("mode") or "agent")

    def get_analytics(self) -> dict[str, Any]:
        from job_hunter.metrics.store import get_runs
        from job_hunter.metrics.telemetry import get_telemetry_summary

        db_path = self._root / "outputs" / "state" / "metrics.db"
        runs = get_runs(db_path)
        # agent mode never writes pipeline_runs (job-hunter hunt only scrapes; skills
        # invoked via /job-hunter batch drive tokens, captured only in telemetry below).
        # llm-api mode writes both: pipeline_runs per hunt/tailor run, plus telemetry
        # broken out by LLM role (jd_extraction/scoring/tailoring/...).
        return {"mode": self._config_mode(), "runs": runs, "telemetry": get_telemetry_summary(db_path)}

    def _doctor_warnings(self) -> list[str]:
        from job_hunter.ux.health import doctor

        try:
            result = doctor(self._root)
        except Exception:  # noqa: BLE001 — a successful save must never be reported as failed
            return []
        return [f"{check['name']}: {check['detail']}" for check in result["checks"] if not check["ok"]]

    def _config_result(self, result: dict[str, Any], extra_data: dict[str, Any] | None = None) -> dict[str, Any]:
        data = {"revision": result["revision"], **(extra_data or {})}
        warnings = list(result.get("warnings", []))
        if result["ok"]:
            warnings.extend(self._doctor_warnings())
        return {
            "ok": result["ok"],
            "data": data if result["ok"] else None,
            "errors": result["errors"],
            "warnings": warnings,
        }

    def get_job_hunter_config_form(self) -> dict[str, Any]:
        import yaml

        from job_hunter.config import service

        raw = service.read_job_hunter_config(self._root)
        try:
            parsed = yaml.safe_load(raw["data"]) or {}
        except yaml.YAMLError as exc:
            return {"ok": False, "data": None, "errors": [f"Invalid YAML on disk: {exc}"], "warnings": []}
        if isinstance(parsed, dict):
            from job_hunter.config.locations import canonicalize_config_regions

            parsed = canonicalize_config_regions(parsed)
        form = service.config_to_form(parsed) if isinstance(parsed, dict) else service.config_to_form({})
        return {"ok": True, "data": {"form": form, "revision": raw["revision"]}, "errors": [], "warnings": []}

    def get_location_countries(self) -> dict[str, Any]:
        from job_hunter.locations import countries

        return {"ok": True, "countries": countries()}

    def get_filter_options(self) -> dict[str, Any]:
        from job_hunter.filters import filter_options

        return {"ok": True, **filter_options()}

    def get_location_cities(
        self, country: str, query: str = "", selected_id: str = "", limit: int = 250
    ) -> dict[str, Any]:
        from job_hunter.locations import cities, city_by_id, city_by_name_exact, normalize_location_name

        code = country.strip().upper()
        all_cities = cities(code)
        needle = normalize_location_name(query)
        exact = city_by_name_exact(code, query) if needle else None
        matches = (
            [exact]
            if exact is not None
            else [city for city in all_cities if not needle or needle in normalize_location_name(city.name)]
        )
        page_size = max(20, min(int(limit), 500))
        page = list(matches[:page_size])
        selected = city_by_id(code, selected_id)
        if selected is not None and all(city.id != selected.id for city in page):
            page.append(selected)
        return {
            "ok": True,
            "country": code,
            "cities": [{"id": city.id, "name": city.name} for city in page],
            "total": len(matches),
        }

    def save_job_hunter_config_form(self, form: dict[str, Any], revision: str) -> dict[str, Any]:
        import yaml

        from job_hunter.config import service

        raw = service.read_job_hunter_config(self._root)
        try:
            parsed = yaml.safe_load(raw["data"]) or {}
        except yaml.YAMLError as exc:
            return {"ok": False, "data": None, "errors": [f"Invalid YAML on disk: {exc}"], "warnings": []}
        merged = service.apply_form_to_config(parsed if isinstance(parsed, dict) else {}, form)
        new_text = yaml.safe_dump(merged, sort_keys=False, allow_unicode=True)
        result = service.save_job_hunter_config(self._root, new_text, revision)
        return self._config_result(result)

    def get_job_hunter_config_raw(self) -> dict[str, Any]:
        from job_hunter.config import service

        raw = service.read_job_hunter_config(self._root)
        return {"ok": True, "data": {"text": raw["data"], "revision": raw["revision"]}, "errors": [], "warnings": []}

    def save_job_hunter_config_raw(self, text: str, revision: str) -> dict[str, Any]:
        from job_hunter.config import service

        result = service.save_job_hunter_config(self._root, text, revision)
        return self._config_result(result)

    def undo_job_hunter_config(self) -> dict[str, Any]:
        from job_hunter.config import service

        result = service.undo_last_save(self._root, "job_hunter_config")
        return self._config_result(result)

    def get_career_context(self) -> dict[str, Any]:
        from job_hunter.config import service

        raw = service.read_career_context(self._root)
        return {"ok": True, "data": {"text": raw["data"], "revision": raw["revision"]}, "errors": [], "warnings": []}

    def save_career_context(self, text: str, revision: str) -> dict[str, Any]:
        from job_hunter.config import service

        result = service.save_career_context(self._root, text, revision)
        return {
            "ok": result["ok"],
            "data": {"revision": result["revision"]} if result["ok"] else None,
            "errors": result["errors"],
            "warnings": result["warnings"],
        }

    def undo_career_context(self) -> dict[str, Any]:
        from job_hunter.config import service

        result = service.undo_last_save(self._root, "career_context")
        return {
            "ok": result["ok"],
            "data": {"revision": result["revision"]} if result["ok"] else None,
            "errors": result["errors"],
            "warnings": result["warnings"],
        }

    def get_resume_style(self) -> dict[str, Any]:
        from job_hunter.config import service
        from job_hunter.config.resume_style import read_resume_style

        resume = service.read_resume_tex(self._root)
        style = read_resume_style(resume["data"])
        if not style["ok"]:
            return {"ok": False, "data": None, "errors": [style["error"]], "warnings": []}
        return {"ok": True, "data": {**style, "revision": resume["revision"]}, "errors": [], "warnings": []}

    def save_resume_style(self, choices: dict[str, Any], revision: str) -> dict[str, Any]:
        from job_hunter.config import service
        from job_hunter.config.resume_style import apply_resume_style

        resume = service.read_resume_tex(self._root)
        try:
            new_text = apply_resume_style(resume["data"], choices)
        except ValueError as exc:
            return {"ok": False, "data": None, "errors": [str(exc)], "warnings": []}
        result = service.save_resume_style(self._root, new_text, revision)
        return {
            "ok": result["ok"],
            "data": {"revision": result["revision"]} if result["ok"] else None,
            "errors": result["errors"],
            "warnings": result["warnings"],
        }

    def _companies_with_latest_result(
        self, companies: list[dict[str, Any]], url_key: str = "career_url"
    ) -> list[dict[str, Any]]:
        from job_hunter.tracking import company_hunts

        latest_by_url = company_hunts.get_latest_task_by_url(self._root)
        decorated = []
        for company in companies:
            entry = dict(company)
            latest = latest_by_url.get(str(company.get(url_key) or ""))
            entry["latest_result"] = (
                {
                    "status": latest["status"],
                    "finished_at": latest["finished_at"],
                    "jobs_inserted": latest["jobs_inserted"],
                    "failure_reason": latest["failure_reason"],
                }
                if latest
                else None
            )
            decorated.append(entry)
        return decorated

    def _enabled_filter_bool(self, enabled_filter: str) -> bool | None:
        return True if enabled_filter == "enabled" else False if enabled_filter == "disabled" else None

    # ── My Companies (config/job_hunter.yml's companies.targets) ──

    def get_company_targets(self) -> dict[str, Any]:
        from job_hunter.config import service

        result = service.read_company_targets(self._root)
        companies = self._companies_with_latest_result(result["data"]["targets"], url_key="url")
        return {
            "ok": True,
            "data": {"companies": companies, "revision": result["revision"]},
            "errors": [],
            "warnings": [],
        }

    def save_company_targets(self, targets: list[dict[str, Any]], revision: str) -> dict[str, Any]:
        from job_hunter.companies import store
        from job_hunter.config import service

        result = service.save_company_targets(self._root, targets, revision)
        if not result["ok"]:
            return {"ok": False, "data": None, "errors": result["errors"], "warnings": result["warnings"]}
        fresh = service.read_company_targets(self._root)
        store.sync_user_targets(self._root, fresh["data"]["targets"])
        return {
            "ok": True,
            "data": {
                "companies": self._companies_with_latest_result(fresh["data"]["targets"], url_key="url"),
                "revision": fresh["revision"],
            },
            "errors": [],
            "warnings": result["warnings"],
        }

    def undo_company_targets(self) -> dict[str, Any]:
        from job_hunter.companies import store
        from job_hunter.config import service

        result = service.undo_last_save(self._root, "job_hunter_config")
        if not result["ok"]:
            return {"ok": False, "data": None, "errors": result["errors"], "warnings": result["warnings"]}
        fresh = service.read_company_targets(self._root)
        store.sync_user_targets(self._root, fresh["data"]["targets"])
        return {
            "ok": True,
            "data": {
                "companies": self._companies_with_latest_result(fresh["data"]["targets"], url_key="url"),
                "revision": fresh["revision"],
            },
            "errors": [],
            "warnings": [],
        }

    def open_company_target(self, url: str) -> dict[str, Any]:
        from job_hunter.config import service

        targets = service.read_company_targets(self._root)["data"]["targets"]
        known_urls = {str(t.get("url") or "") for t in targets if isinstance(t, dict)}
        if url not in known_urls or urlsplit(url).scheme != "https":
            return {"ok": False, "error": "Unknown or invalid company URL."}
        try:
            _open_url(url)
        except OSError:
            return {"ok": False, "error": "Could not open URL."}
        return {"ok": True}

    def open_config_folder(self) -> dict[str, Any]:
        return self._launch(self._root / "config")

    # ── Shared catalog browse (package-owned companies, opt-in per company or filter) ──

    def get_catalog_industries(self) -> dict[str, Any]:
        """Industry list + company counts, for the Shared Catalog filter dropdown."""
        from job_hunter.companies import store
        from job_hunter.filters.catalog import load_filter_catalog

        store.ensure_seeded(self._root)
        counts = {row["industry"]: row["count"] for row in store.industry_counts(self._root, source="catalog")}
        industries = [
            {"id": industry.id, "label": industry.label, "count": counts[industry.id]}
            for industry in load_filter_catalog().industries
            if counts.get(industry.id)
        ]
        return {"ok": True, "data": {"industries": industries}}

    def get_catalog_countries(self) -> dict[str, Any]:
        """Distinct countries present in the catalog, for the Shared Catalog filter dropdown."""
        from job_hunter.companies import store

        store.ensure_seeded(self._root)
        return {"ok": True, "data": {"countries": store.distinct_countries(self._root, source="catalog")}}

    def get_catalog_page(
        self,
        industry: str = "",
        search: str = "",
        page: int = 1,
        page_size: int = 100,
        enabled_filter: str = "",
        country: str = "",
        city: str = "",
        company_type: str = "",
        funding_stage: str = "",
    ) -> dict[str, Any]:
        """Server-paginated browse of the bundled catalog with current opt-in state.

        enabled_filter: "" (all) | "enabled" | "disabled".
        """
        from job_hunter.companies import store

        store.ensure_seeded(self._root)
        result = store.query_page(
            self._root,
            source="catalog",
            industry=industry,
            search=search,
            enabled=self._enabled_filter_bool(enabled_filter),
            country=country,
            city=city,
            company_type=company_type,
            funding_stage=funding_stage,
            page=page,
            page_size=page_size,
        )
        return {"ok": True, "data": result}

    def save_catalog_enabled_ids(self, ids: list[int], enabled: bool) -> dict[str, Any]:
        """Bulk enable/disable the currently-selected catalog rows (by store id)."""
        from job_hunter.companies import store

        n = store.set_enabled(self._root, ids, enabled)
        return {"ok": True, "data": {"count": n}, "errors": [], "warnings": []}

    def open_catalog_company(self, company_id: int) -> dict[str, Any]:
        """Open a bundled catalog company's career page by store id — looked up from our
        own trusted store, not an arbitrary URL string from the caller."""
        from job_hunter.companies import store

        company = store.get_by_id(self._root, company_id)
        if company is None or company["source"] != "catalog":
            return {"ok": False, "error": "Unknown catalog company."}
        try:
            _open_url(company["url"])
        except OSError:
            return {"ok": False, "error": "Could not open URL."}
        return {"ok": True}

    def set_catalog_filter_enabled(
        self,
        industry: str,
        search: str,
        enabled_filter: str,
        country: str,
        city: str,
        enabled: bool,
        company_type: str = "",
        funding_stage: str = "",
    ) -> dict[str, Any]:
        """Enable/disable every catalog company matching the current browse filter in one
        query — avoids shipping N ids for "enable all shown" at 100k-company scale."""
        from job_hunter.companies import store

        n = store.set_enabled_where(
            self._root,
            source="catalog",
            industry=industry,
            search=search,
            enabled=self._enabled_filter_bool(enabled_filter),
            country=country,
            city=city,
            company_type=company_type,
            funding_stage=funding_stage,
            new_enabled=enabled,
        )
        return {"ok": True, "data": {"count": n}, "errors": [], "warnings": []}

    def get_user_name(self) -> str:
        """Extract candidate name from LaTeX resume via \\name{...}."""
        import re

        from job_hunter.config.loader import get_config

        config = get_config("job_hunter")
        tex_rel = config.get("profile", {}).get("resume_tex", "profile/resume_double_column.tex")
        tex_path = self._root / tex_rel
        if tex_path.exists():
            m = re.search(r"\\name\{([^}]+)\}", tex_path.read_text(encoding="utf-8"))
            if m:
                return m.group(1).strip()
        return ""
