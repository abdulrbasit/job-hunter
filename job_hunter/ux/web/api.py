"""Python JS API exposed to the pywebview dashboard via window.pywebview.api.*"""

from __future__ import annotations

import base64
import json
import os
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


class DashAPI:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._hunt_lock = threading.Lock()
        self._hunt_status: dict[str, Any] = {"state": "idle"}

    def get_applications(self) -> list[dict[str, Any]]:
        from job_hunter.tracking.applications import filtered_applications

        applications = [dict(app) for app in filtered_applications(root=self._root)]
        for app in applications:
            slug_date = str(app.get("slug") or "")[:10]
            app["date"] = (
                app.get("date")
                or (slug_date if len(slug_date) == 10 and slug_date[4:5] == "-" and slug_date[7:8] == "-" else "")
                or str(app.get("discovered_at") or app.get("created_at") or "")[:10]
            )
        return applications

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
        except (ValueError, KeyError) as exc:
            return {"error": str(exc)}
        self._refresh_readme()
        return result

    def delete_application(self, slug: str) -> dict[str, Any]:
        from job_hunter.tracking.applications import delete_application

        try:
            delete_application(slug, self._root)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        self._refresh_readme()
        return {"ok": True, "error": ""}

    def delete_applications_batch(self, slugs: list[str]) -> dict[str, Any]:
        """One backend call for N application deletes — README refreshes once, not per slug."""
        from job_hunter.tracking.applications import delete_applications_batch

        try:
            result = delete_applications_batch([str(slug) for slug in slugs], root=self._root)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "deleted": 0, "skipped": [], "warnings": []}
        self._refresh_readme()
        return {
            "ok": True,
            "error": "",
            "deleted": result["deleted"],
            "skipped": result["skipped"],
            "warnings": result["warnings"],
        }

    def get_unprocessed(self) -> dict[str, Any]:
        from job_hunter.tracking.repository import display_status, get_jobs_summary

        def visible(statuses: tuple[str, ...]) -> list[dict[str, Any]]:
            return [
                {
                    "id": job.get("id"),
                    "company": job.get("company"),
                    "title": job.get("title"),
                    "location": job.get("location"),
                    "status": display_status(str(job.get("status") or "")),
                    "url": job.get("url"),
                    "date": str(job.get("discovered_at") or job.get("created_at") or "")[:10],
                }
                for job in get_jobs_summary(self._root, statuses=statuses)
                if str(job.get("title") or "").strip() and str(job.get("company") or "").strip()
            ]

        active = visible(("candidate", "discovered"))
        discarded = visible(("discarded", "processed"))
        return {
            "active": active,
            "discarded": discarded,
            "counts": {"active": len(active), "discarded": len(discarded), "total": len(active) + len(discarded)},
        }

    def discard_unprocessed(self, job_id: int) -> dict[str, Any]:
        """Move one candidate to status='discarded' (never touches applications)."""
        from job_hunter.tracking.repository import set_status_by_id

        try:
            set_status_by_id(self._root, int(job_id), "discarded")
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "error": ""}

    def discard_unprocessed_batch(self, job_ids: list[int]) -> dict[str, Any]:
        """One backend call for N candidate discards — replaces per-id Promise.all fan-out."""
        from job_hunter.tracking.repository import discard_job_ids

        try:
            result = discard_job_ids(self._root, [int(job_id) for job_id in job_ids])
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc), "discarded": 0, "skipped": []}
        return {"ok": True, "error": "", "discarded": result["discarded"], "skipped": result["skipped"]}

    def delete_unprocessed(self, job_id: int) -> dict[str, Any]:
        from job_hunter.tracking.repository import delete_job_by_id

        try:
            delete_job_by_id(self._root, int(job_id))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "error": ""}

    def run_company_hunt(self) -> dict[str, Any]:
        """Kick off the company career-page browser hunt in the background."""
        with self._hunt_lock:
            if self._hunt_status.get("state") == "running":
                return {"already_running": True}
            self._hunt_status = {"state": "running"}
        self._hunt_thread = threading.Thread(target=self._run_company_hunt_worker, daemon=True)
        self._hunt_thread.start()
        return {"started": True}

    def _update_hunt_progress(self, event: dict[str, Any]) -> None:
        step = event.get("step")
        with self._hunt_lock:
            status = self._hunt_status
            if step == "started":
                self._hunt_status = {
                    "state": "running",
                    "total": event.get("total", 0),
                    "checked": 0,
                    "current_company": "",
                    "companies": [],
                }
            elif step == "company-checking":
                status["current_company"] = event.get("company", "")
            elif step == "company-done":
                status["companies"].append(
                    {"company": event.get("company", ""), "status": "ok", "jobs_found": event.get("jobs_found", 0)}
                )
                status["checked"] = len(status["companies"])
            elif step == "company-failed":
                status["companies"].append(
                    {"company": event.get("company", ""), "status": "failed", "reason": event.get("reason", "")}
                )
                status["checked"] = len(status["companies"])
            elif step == "finished":
                status["succeeded"] = event.get("succeeded", 0)
                status["failed"] = event.get("failed", 0)
            elif step == "fatal":
                self._hunt_status = {"state": "error", "error": event.get("reason") or "Something went wrong."}

    @staticmethod
    def _hunt_message(status: dict[str, Any], inserted: int) -> str:
        total = status.get("total", 0)
        failed = status.get("failed", 0)
        candidates = "candidate" if inserted == 1 else "candidates"
        if not failed:
            return f"{total} companies checked, {inserted} new {candidates} found."
        ok = total - failed
        return f"{ok} of {total} companies checked ({failed} couldn't be reached). {inserted} new {candidates} found."

    def _run_company_hunt_worker(self) -> None:
        from job_hunter.pipeline import browser_hunt
        from job_hunter.tracking.repository import get_jobs_summary

        before = len(get_jobs_summary(self._root, statuses=("candidate",)))
        try:
            browser_hunt.run(on_progress=self._update_hunt_progress)
        except Exception:  # noqa: BLE001
            with self._hunt_lock:
                self._hunt_status = {
                    "state": "error",
                    "error": "Something went wrong while checking company career pages. Try again in a moment.",
                }
            return

        with self._hunt_lock:
            if self._hunt_status.get("state") == "error":
                return  # a "fatal" progress event already set this — don't clobber it with "done"
            after = len(get_jobs_summary(self._root, statuses=("candidate",)))
            inserted = max(0, after - before)
            self._hunt_status["state"] = "done"
            self._hunt_status["inserted"] = inserted
            self._hunt_status["message"] = self._hunt_message(self._hunt_status, inserted)

    def get_company_hunt_status(self) -> dict[str, Any]:
        with self._hunt_lock:
            status = dict(self._hunt_status)
            if "companies" in status:
                status["companies"] = list(status["companies"])
            return status

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
        form = service.config_to_form(parsed) if isinstance(parsed, dict) else service.config_to_form({})
        return {"ok": True, "data": {"form": form, "revision": raw["revision"]}, "errors": [], "warnings": []}

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

    def get_career_pages(self) -> dict[str, Any]:
        from job_hunter.config import service

        result = service.read_career_pages(self._root)
        return {
            "ok": True,
            "data": {"companies": result["data"]["companies"], "revision": result["revision"]},
            "errors": [],
            "warnings": [],
        }

    def save_career_pages(self, companies: list[dict[str, Any]], revision: str) -> dict[str, Any]:
        from job_hunter.config import service

        result = service.save_career_pages(self._root, companies, revision)
        if not result["ok"]:
            return {"ok": False, "data": None, "errors": result["errors"], "warnings": result["warnings"]}
        fresh = service.read_career_pages(self._root)
        return {
            "ok": True,
            "data": {"companies": fresh["data"]["companies"], "revision": fresh["revision"]},
            "errors": [],
            "warnings": result["warnings"],
        }

    def undo_career_pages(self) -> dict[str, Any]:
        from job_hunter.config import service

        result = service.undo_last_save(self._root, "career_pages")
        if not result["ok"]:
            return {"ok": False, "data": None, "errors": result["errors"], "warnings": result["warnings"]}
        fresh = service.read_career_pages(self._root)
        return {
            "ok": True,
            "data": {"companies": fresh["data"]["companies"], "revision": fresh["revision"]},
            "errors": [],
            "warnings": [],
        }

    def open_career_page(self, url: str) -> dict[str, Any]:
        from job_hunter.config import service

        pages = service.read_career_pages(self._root)
        known_urls = {
            str(company.get("career_url") or "") for company in pages["data"]["companies"] if isinstance(company, dict)
        }
        if url not in known_urls:
            return {"ok": False, "error": "Unknown career page URL."}
        if urlsplit(url).scheme not in ("http", "https"):
            return {"ok": False, "error": "Only http/https URLs can be opened."}
        try:
            _open_url(url)
        except OSError:
            return {"ok": False, "error": "Could not open URL."}
        return {"ok": True}

    def open_career_pages_file(self) -> dict[str, Any]:
        return self._launch(self._root / "config" / "career_pages.yml")

    def open_config_folder(self) -> dict[str, Any]:
        return self._launch(self._root / "config")

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
