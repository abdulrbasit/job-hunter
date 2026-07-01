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
        "job-hunter internal commit-job",
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
        "job-hunter internal commit-job",
        "job-hunter internal finalize-run",
        "job-hunter internal mark-processed",
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

    assert "job-hunter internal agent-context lifecycle" in process_batch


def test_process_batch_never_pauses_between_inline_phases() -> None:
    process_batch = (ROOT / ".claude" / "skills" / "job-hunter" / "modes" / "batch.md").read_text(encoding="utf-8")

    assert "Non-Interactive Contract" in process_batch
    assert "Shall I continue?" in process_batch
    assert "atomic skill returns to caller" in process_batch
    assert "PDF failure non-blocking only when `resume_tailored.tex` exists" in process_batch
    assert "job-hunter internal cleanup-transient" in process_batch


def test_atomic_skills_return_control_without_waiting() -> None:
    for skill_name in ("research", "tailor"):
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
    assert "job-hunter internal compile-pdf --job <slug>" in text


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

    assert "job-hunter internal discard-job --job <slug>" in text
    assert "job-hunter internal agent-context validate-score --path " in text
    assert "job-hunter internal compile-pdf --job <slug>" in text
    assert "--resume-batch" not in text


def test_tailor_skill_calls_tailor_context_command() -> None:
    text = (ROOT / ".claude" / "skills" / "job-hunter" / "modes" / "tailor.md").read_text(encoding="utf-8")

    assert "agent-context tailor-context" in text
    assert "--job <slug>" in text


def test_tailor_skill_enforces_cover_letter_constraints() -> None:
    text = (ROOT / ".claude" / "skills" / "job-hunter" / "modes" / "tailor.md").read_text(encoding="utf-8")

    assert "target_words" in text
    assert "max_words" in text
    assert "cover_constraints" in text
    assert "paragraph_structure" in text


def test_tailor_skill_enforces_tailoring_rules() -> None:
    text = (ROOT / ".claude" / "skills" / "job-hunter" / "modes" / "tailor.md").read_text(encoding="utf-8")

    assert "tailoring_rules" in text
    assert "positioning_rules" in text
    assert "project_rules" in text
    assert "keywords" in text
    assert "gaps" in text


def test_user_facing_skills_are_mirrored_byte_identical_into_workspace_template() -> None:
    """.claude/skills/ is the source of truth; the bundled workspace template copy must match.

    Dev-only skills (job_hunter.workspace._assets._DEV_SKILL_DIRS) are intentionally excluded
    from the template and are skipped here.
    """
    from job_hunter.workspace._assets import _DEV_SKILL_DIRS

    root_skills = ROOT / ".claude" / "skills"
    template_skills = ROOT / "job_hunter" / "templates" / "workspace" / ".claude" / "skills"

    mismatches: list[str] = []
    for skill_dir in sorted(p for p in root_skills.iterdir() if p.is_dir()):
        if skill_dir.name in _DEV_SKILL_DIRS:
            continue
        for source_file in skill_dir.rglob("*"):
            if not source_file.is_file():
                continue
            rel = source_file.relative_to(root_skills)
            mirrored = template_skills / rel
            if not mirrored.exists():
                mismatches.append(f"missing in template: {rel.as_posix()}")
            elif mirrored.read_bytes() != source_file.read_bytes():
                mismatches.append(f"content drift: {rel.as_posix()}")

    assert mismatches == [], f"skill/template drift: {mismatches}"


def test_rules_md_is_the_file_agents_md_flags_as_manually_mirrored() -> None:
    """Guards the specific drift risk AGENTS.md calls out by name."""
    root_rules = ROOT / ".claude" / "skills" / "job-hunter" / "_rules.md"
    template_rules = ROOT / "job_hunter" / "templates" / "workspace" / ".claude" / "skills" / "job-hunter" / "_rules.md"

    assert root_rules.read_text(encoding="utf-8") == template_rules.read_text(encoding="utf-8")
