"""Company browser hunt: runs the career-page extraction ladder per enabled company.

Enabled companies come from job_hunter.companies.hunt_candidates — the runtime store
(package catalog opt-ins + config/job_hunter.yml's companies.targets), gated by the
user's enabled regions and excluded industries.

Writes results to outputs/state/jobs.db (status='candidate'), the same store the regular
find-jobs hunt uses — so browser-hunt candidates get deduped, screened, scored, and tailored
through the exact same downstream pipeline, not a separate isolated file.

Every company's task row is persisted (company_hunt_tasks) the moment it finishes, and
tasks are precreated as 'pending' before any work starts — a crash mid-run leaves the
first N companies as 'ok'/'failed' and the rest 'pending', so mode="resume" can continue
exactly where it left off instead of restarting from zero.
"""

from __future__ import annotations

import inspect
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from yaml import YAMLError

from job_hunter.companies import hunt_candidates
from job_hunter.config.loader import ROOT, get_job_hunter_config_for_root
from job_hunter.locations import canonical_locations_for_job
from job_hunter.pipeline.stages.screening import screen_jobs_by_rules
from job_hunter.sources.career_pages import extract_career_page_jobs
from job_hunter.sources.career_pages._rendering import ensure_chromium_installed, extract_playwright_jobs_batch
from job_hunter.tracking import company_hunts
from job_hunter.tracking.repository import insert_jobs_with_new_count

logger = logging.getLogger(__name__)

Progress = Callable[[dict[str, Any]], None]
CHEAP_WORKERS = 8
PLAYWRIGHT_WORKERS = 2
COMPANY_DEADLINE_SECONDS = 120.0


def _friendly_reason(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "took too long to respond"
    if "connection" in name:
        return "couldn't be reached"
    return "couldn't be checked right now"


def _is_stale(finished_at: str, cooldown_hours: float) -> bool:
    if not finished_at:
        return True
    try:
        finished = datetime.fromisoformat(finished_at)
    except ValueError:
        return True
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=UTC)
    return datetime.now(UTC) - finished > timedelta(hours=cooldown_hours)


def _select_companies_for_mode(
    root: Path, companies: list[Any], mode: str, cooldown_hours: float
) -> tuple[list[Any], list[Any]]:
    """Return (to_process, to_skip) for the given run mode.

    force_all processes everyone (preserves pre-persistence behavior). failed_only
    retries companies that have never succeeded. new_changed (the default) retries
    companies with no successful task, or whose last success is older than the
    cooldown — a recent unchanged success is skipped.
    """
    if mode == company_hunts.MODE_FORCE_ALL:
        return list(companies), []

    to_process: list[Any] = []
    to_skip: list[Any] = []
    for company in companies:
        url = company.get("career_url", "") if isinstance(company, dict) else ""
        last = company_hunts.get_last_task_for_url(root, url) if url else None

        if mode == company_hunts.MODE_FAILED_ONLY:
            if last is None or last["status"] == company_hunts.FAILED:
                to_process.append(company)
            else:
                to_skip.append(company)
            continue

        # new_changed (default)
        if last is None or last["status"] != company_hunts.OK or _is_stale(last.get("finished_at", ""), cooldown_hours):
            to_process.append(company)
        else:
            to_skip.append(company)
    return to_process, to_skip


def _supports_keyword(function: Callable[..., Any], name: str) -> bool:
    try:
        return name in inspect.signature(function).parameters
    except (TypeError, ValueError):
        return False


def _cheap_extract(company: dict[str, Any], titles: list[str]) -> tuple[list[dict], bool]:
    """Return cheap-stage jobs and whether browser fallback is still needed."""
    if _supports_keyword(extract_career_page_jobs, "use_playwright"):
        return extract_career_page_jobs(company, titles, use_playwright=False), True
    return extract_career_page_jobs(company, titles), False


def _timed_cheap_extract(company: dict[str, Any], titles: list[str]) -> tuple[list[dict], bool, float]:
    """Times only this company's own extraction, from when a pool worker actually picks it
    up — not from task creation. With CHEAP_WORKERS=8 and thousands of enabled companies,
    queue-wait alone can exceed COMPANY_DEADLINE_SECONDS long before a
    company's own turn comes up if duration is measured from task creation instead."""
    started_at = time.monotonic()
    jobs, needs_playwright = _cheap_extract(company, titles)
    return jobs, needs_playwright, time.monotonic() - started_at


def run(  # noqa: C901
    *,
    on_progress: Progress | None = None,
    mode: str = company_hunts.MODE_NEW_CHANGED,
    cooldown_hours: float = company_hunts.DEFAULT_COOLDOWN_HOURS,
) -> int:
    emit = on_progress or (lambda _event: None)
    root = Path(ROOT)
    if not (root / "config" / "job_hunter.yml").exists():
        emit({"step": "fatal", "reason": "config/job_hunter.yml could not be read"})
        return 1
    try:
        config = get_job_hunter_config_for_root(root)
    except (YAMLError, ValueError, OSError):
        logger.exception("[browser-hunt] failed to read config")
        emit({"step": "fatal", "reason": "config/job_hunter.yml could not be read"})
        return 1

    titles = config.get("job_titles", [])
    enabled_companies = hunt_candidates(root, config)
    metadata_by_url = {str(company["career_url"]): company for company in enabled_companies}

    if not enabled_companies:
        logger.info("[browser-hunt] no companies enabled — nothing to do")
        return 0

    resumed_run = company_hunts.find_resumable_run(root) if mode == company_hunts.MODE_RESUME else None
    if resumed_run:
        run_id = resumed_run["id"]
        total = resumed_run["total"]
        company_hunts.prepare_resume(root, run_id)
        pending_tasks = company_hunts.get_pending_tasks(root, run_id)
    else:
        effective_mode = company_hunts.MODE_NEW_CHANGED if mode == company_hunts.MODE_RESUME else mode
        to_process, to_skip = _select_companies_for_mode(root, enabled_companies, effective_mode, cooldown_hours)
        run_id = company_hunts.begin_run(root, effective_mode)
        company_hunts.create_tasks(root, run_id, to_process, status=company_hunts.PENDING)
        company_hunts.create_tasks(root, run_id, to_skip, status=company_hunts.SKIPPED)
        total = len(enabled_companies)
        pending_tasks = company_hunts.get_pending_tasks(root, run_id)

    emit({"step": "started", "total": total})
    hunt_run_tag = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    terminal: set[int] = set()
    terminal_lock = threading.Lock()
    started_at: dict[int, float] = {}

    def finish_failed(task: dict[str, Any], reason: str, duration: float) -> None:
        with terminal_lock:
            if task["id"] in terminal:
                return
            terminal.add(task["id"])
        company_hunts.finish_task(
            root,
            task["id"],
            run_id,
            status=company_hunts.FAILED,
            duration_s=duration,
            failure_reason=reason,
        )
        emit({"step": "company-failed", "total": total, "company": task["company_name"] or "?", "reason": reason})

    def finish_success(task: dict[str, Any], jobs: list[dict], duration: float) -> None:
        if duration > COMPANY_DEADLINE_SECONDS:
            finish_failed(task, "took too long to respond", duration)
            return
        scoped_jobs = []
        company_metadata = metadata_by_url.get(str(task["career_url"]), {})
        for job in jobs:
            scoped = {
                **job,
                "location": job.get("location") or task["location"],
                "company_type": company_metadata.get("company_type", "unknown"),
                "funding_stage": company_metadata.get("funding_stage"),
            }
            scoped["canonical_locations"] = [item.model_dump() for item in canonical_locations_for_job(scoped)]
            scoped_jobs.append(scoped)
        kept, rejected = screen_jobs_by_rules(scoped_jobs, config)
        if rejected:
            logger.info(
                "[browser-hunt] %s: %d jobs excluded by policy before insert",
                task["company_name"],
                len(rejected),
            )
        counts = insert_jobs_with_new_count(root, kept, run_id=hunt_run_tag) if kept else {"processed": 0, "new": 0}
        extraction_method = jobs[0].get("extraction_method", "") if jobs else ""
        with terminal_lock:
            if task["id"] in terminal:
                return
            terminal.add(task["id"])
        company_hunts.finish_task(
            root,
            task["id"],
            run_id,
            status=company_hunts.OK,
            extraction_method=extraction_method,
            duration_s=duration,
            jobs_observed=len(jobs),
            jobs_inserted=counts["new"],
        )
        logger.info("[browser-hunt] %s: %d jobs", task["company_name"], len(jobs))
        emit(
            {
                "step": "company-done",
                "total": total,
                "company": task["company_name"] or "?",
                "jobs_found": len(jobs),
            }
        )

    ready_tasks: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for index, task in enumerate(pending_tasks, start=1):
        name = task["company_name"] or "?"
        emit({"step": "company-checking", "index": index, "total": total, "company": name})
        if not task["career_url"]:
            finish_failed(task, "no career_url configured", 0.0)
            continue
        company_hunts.start_task(root, task["id"])
        started_at[task["id"]] = time.monotonic()
        ready_tasks.append(
            (
                task,
                {
                    "name": task["company_name"],
                    "career_url": task["career_url"],
                    "location": task["location"],
                    "_task_id": task["id"],
                },
            )
        )

    fallback: list[tuple[dict[str, Any], dict[str, Any]]] = []
    with ThreadPoolExecutor(max_workers=min(CHEAP_WORKERS, len(ready_tasks)) or 1) as pool:
        futures = {pool.submit(_timed_cheap_extract, company, titles): (task, company) for task, company in ready_tasks}
        for future in as_completed(futures):
            task, company = futures[future]
            try:
                jobs, needs_playwright, duration = future.result()
            except Exception as exc:  # noqa: BLE001
                # Task never started_at-timestamped its own attempt (it raised before
                # returning one) — fall back to the queue-inclusive duration for logging
                # purposes only; _friendly_reason doesn't consult it.
                duration = time.monotonic() - started_at[task["id"]]
                logger.warning("[browser-hunt] %s: failed (%s)", task["company_name"], exc)
                finish_failed(task, _friendly_reason(exc), duration)
                continue
            if jobs or not needs_playwright:
                finish_success(task, jobs, duration)
            elif duration > COMPANY_DEADLINE_SECONDS:
                finish_failed(task, "took too long to respond", duration)
            else:
                fallback.append((task, company))

    if fallback:
        if not ensure_chromium_installed():
            for task, _company in fallback:
                finish_failed(task, "Chromium unavailable; run 'playwright install chromium'", 0.0)
        else:
            task_by_id = {task["id"]: task for task, _company in fallback}

            def on_browser_result(company: dict, jobs: list[dict], duration: float) -> None:
                # duration is this company's own render time (from extract_playwright_jobs_batch),
                # not time.monotonic() - started_at[task["id"]] — with a 2-worker pool and a
                # fallback queue that can run into the thousands, queue-wait alone can dwarf
                # COMPANY_DEADLINE_SECONDS long before a company's own turn comes up, which
                # falsely marked companies that rendered fine as "took too long to respond".
                task = task_by_id[company["_task_id"]]
                finish_success(task, jobs, duration)

            worker_count = min(PLAYWRIGHT_WORKERS, len(fallback))
            chunks = [fallback[index::worker_count] for index in range(worker_count)]
            with ThreadPoolExecutor(max_workers=worker_count) as pool:
                browser_futures = [
                    (
                        pool.submit(
                            extract_playwright_jobs_batch,
                            [company for _task, company in chunk],
                            titles,
                            on_result=on_browser_result,
                        ),
                        chunk,
                    )
                    for chunk in chunks
                ]
                for future, chunk in browser_futures:
                    try:
                        future.result()
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("[browser-hunt] Playwright worker failed: %s", exc)
                        for task, _company in chunk:
                            finish_failed(
                                task,
                                "couldn't be checked right now",
                                time.monotonic() - started_at[task["id"]],
                            )

    company_hunts.finish_run(root, run_id, status="done")
    summary = company_hunts.get_run(root, run_id) or {}
    logger.info("[browser-hunt] total=%d → jobs.db (run_id=%s)", summary.get("jobs_inserted", 0), hunt_run_tag)
    emit(
        {
            "step": "finished",
            "total": total,
            "succeeded": summary.get("succeeded", 0),
            "failed": summary.get("failed", 0),
            "jobs_found": summary.get("jobs_inserted", 0),
        }
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(run())
