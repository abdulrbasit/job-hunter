from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _skill_files() -> list[Path]:
    return sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))


def _category(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("category:"):
            return line.split(":", 1)[1].strip()
    return ""


def test_workflow_skills_do_not_use_midflow_handoffs_or_raw_git_commits() -> None:
    forbidden = (
        "Apply `/",
        "Invoke `/",
        "job-hunter commit-job",
        "mark-processed --from-candidates",
        "git commit",
        "git push",
        "commit, push",
        "State committed",
    )
    offenders: list[str] = []
    for path in _skill_files():
        text = path.read_text(encoding="utf-8")
        if _category(text) != "workflow":
            continue
        for pattern in forbidden:
            if pattern in text:
                offenders.append(f"{path.parent.name}: {pattern}")

    assert offenders == []


def test_atomic_skills_do_not_finalize_or_mutate_repo_state() -> None:
    forbidden = (
        "git commit",
        "git push",
        "job-hunter commit-job",
        "job-hunter finalize-run",
        "job-hunter mark-processed",
    )
    offenders: list[str] = []
    for path in _skill_files():
        text = path.read_text(encoding="utf-8")
        if _category(text) != "atomic":
            continue
        for pattern in forbidden:
            if pattern in text:
                offenders.append(f"{path.parent.name}: {pattern}")

    assert offenders == []


def test_setup_does_not_create_auto_run_routine() -> None:
    text = (ROOT / ".claude" / "skills" / "setup" / "SKILL.md").read_text(encoding="utf-8")
    reference = ROOT / ".claude" / "skills" / "setup" / "reference.md"

    assert "auto-run" not in text
    assert "routine setup" not in text
    assert not reference.exists()
    assert "commit, push" not in text


def test_workflow_skills_use_shared_candidate_lifecycle_contract() -> None:
    process_batch = (ROOT / ".claude" / "skills" / "job-hunter" / "modes" / "batch.md").read_text(encoding="utf-8")

    assert "job-hunter agent-context lifecycle" in process_batch


def test_process_batch_never_pauses_between_inline_phases() -> None:
    process_batch = (ROOT / ".claude" / "skills" / "job-hunter" / "modes" / "batch.md").read_text(encoding="utf-8")

    assert 'Never wait for a user to type "Continue"' in process_batch
    assert "status update is not an end state" in process_batch
    assert "control returning to this workflow" in process_batch
    assert "immediately screen that queue" in process_batch
    assert "PDF failure is non-blocking only when `resume_tailored.tex` exists" in process_batch
    assert "job-hunter cleanup-transient" in process_batch


def test_atomic_skills_return_control_without_waiting() -> None:
    for skill_name in ("search", "research", "tailor"):
        text = (ROOT / ".claude" / "skills" / "job-hunter" / "modes" / f"{skill_name}.md").read_text(encoding="utf-8")

        lower = text.lower()
        assert "control returns to the calling workflow" in lower
        assert "caller immediately continues" in lower


def test_tailor_skill_reads_career_context() -> None:
    text = (ROOT / ".claude" / "skills" / "job-hunter" / "modes" / "tailor.md").read_text(encoding="utf-8")

    assert "profile/career_context.md" in text
    assert "resume style" in text
    assert "cover-letter style" in text
    assert "resume_tailored.tex" in text
    assert "outputs/jobs/<slug>/resume_tailored.md" not in text
    assert "job-hunter compile-pdf --job <slug>" in text


def test_search_skill_uses_region_title_query_budget_and_filters() -> None:
    text = (ROOT / ".claude" / "skills" / "job-hunter" / "modes" / "search.md").read_text(encoding="utf-8")

    assert "enabled regions and effective titles" in text
    assert "live, specific job posting" in text
    assert "excluded companies" in text
    assert "excluded title terms" in text
    assert "listing pages" in text
    assert "max_results_per_run" in text
    assert "llm_search_queue.json" in text
    assert "Do not semantically reject industries" in text


def test_single_config_file_is_the_only_config() -> None:
    """All skill config references must point to config/job_hunter.yml, not legacy config files."""

    def old_config(stem: str) -> str:
        return f"config/{stem}_config.yml"

    stale_configs = (
        old_config("search"),
        old_config("scoring"),
        old_config("tailoring"),
        old_config("cover_letter"),
        old_config("api"),
        old_config("job_hunter"),
    )
    offenders: list[str] = []
    for path in _skill_files():
        text = path.read_text(encoding="utf-8")
        for stale in stale_configs:
            if stale in text:
                offenders.append(f"{path.parent.name}: {stale}")
    assert not offenders, f"stale config references in skills: {offenders}"


def test_workflow_skills_do_not_duplicate_jd_fallback_prose() -> None:
    offenders: list[str] = []
    forbidden = (
        "If import-job fails to fetch a JD",
        "If a compact candidate has `jd_status`",
        "same per-candidate processed/WebFetch-fallback rules",
        "Per-candidate `mark-processed` (or WebFetch fallback then drop)",
    )
    for relative in (".claude/skills/job-hunter/modes/batch.md",):
        text = (ROOT / relative).read_text(encoding="utf-8")
        for phrase in forbidden:
            if phrase in text:
                offenders.append(f"{relative}: {phrase}")

    assert offenders == []


def test_url_dedup_state_uses_discovered_urls_not_applied_jobs() -> None:
    """Skills must not reference the old applied_jobs.yml or discovery_cache.yml dedup files."""
    banned = ("applied_jobs.yml", "discovery_cache.yml", "processed_jobs.yml")
    offenders: list[str] = []
    for path in _skill_files():
        text = path.read_text(encoding="utf-8")
        for name in banned:
            if name in text:
                offenders.append(f"{path.parent.name}: {name}")
    assert not offenders, f"stale dedup state references in skills: {offenders}"


def test_job_hunter_modes_use_current_cli_signatures() -> None:
    modes = ROOT / ".claude" / "skills" / "job-hunter" / "modes"
    text = "\n".join(path.read_text(encoding="utf-8") for path in modes.glob("*.md"))

    assert "job-hunter discard-job --job <slug>" in text
    assert "job-hunter agent-context validate-score --path " in text
    assert "job-hunter compile-pdf --job <slug>" in text
    assert "--resume-batch" not in text
