from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from job_hunter.workspace import operations as workspace_ops
from job_hunter.workspace.assets import (
    _iter_source_checkout_files,
    is_dev_only_skill,
    is_resource_only_file,
    iter_managed_files,
    iter_packaged_resource_files,
)
from job_hunter.workspace.manifest import MANIFEST_PATH
from job_hunter.workspace.operations import (
    WorkspaceNotEmptyError,
    iter_template_skill_files,
    run_init,
    update_skills,
    update_workflows,
)


def test_workspace_template_assets_include_config_and_hidden_dirs() -> None:
    paths = {path for path, _content in iter_managed_files()}

    assert "config/job_hunter.yml" in paths
    assert "config/career_pages.yml" not in paths  # retired: company data moved to job_hunter.companies
    assert ".github/workflows/find-jobs.yml" in paths
    assert ".github/searxng/settings.yml" in paths
    assert ".claude/skills/setup/SKILL.md" in paths
    assert ".agents/skills/setup/SKILL.md" in paths
    assert ".env.example" in paths
    assert ".vscode/tasks.json" in paths
    assert ".gitignore" in paths
    assert "outputs/state/discovered_urls.yml" in paths
    assert "data/.gitkeep" not in paths


def test_workspace_gitignore_excludes_rebuildable_source_caches() -> None:
    """Per-source HTTP/computation caches with no downstream reader must not get committed."""
    files = dict(iter_managed_files())
    gitignore = files[".gitignore"].decode("utf-8")

    assert "outputs/state/discovery_cache.yml" in gitignore
    assert "outputs/state/jobicy_feed_cache.json" in gitignore
    assert "outputs/state/metrics.db" in gitignore
    assert "outputs/state/jobs.db-wal" in gitignore
    assert "outputs/state/jobs.db-shm" in gitignore


def test_workspace_template_config_is_valid_yaml() -> None:
    files = dict(iter_managed_files())
    config = yaml.safe_load(files["config/job_hunter.yml"].decode("utf-8"))

    assert config["profile"]["resume_tex"] == "profile/resume_double_column.tex"
    assert "career_context" in config["profile"]
    assert config["job_titles"] == []
    assert config["filters"]["excluded_titles"] == []
    assert config["filters"]["hunt_languages"] == ["en"]
    assert "config/schemas/filter.schema.json" not in files
    assert "linkedin" not in config
    assert "tailoring" not in config
    assert "cover_letter" not in config


def test_workspace_onboarding_is_input_driven_and_documents_prerequisites() -> None:
    files = dict(iter_managed_files())
    onboard = files[".claude/skills/setup/modes/onboard.md"].decode("utf-8")
    onboard_agent = files[".claude/skills/setup/modes/onboard_agent.md"].decode("utf-8")
    onboard_llm = files[".claude/skills/setup/modes/onboard_llm_api.md"].decode("utf-8")
    setup = files["SETUP.md"].decode("utf-8")
    setup_agent = files["SETUP_AGENT.md"].decode("utf-8")
    setup_llm_api = files["SETUP_LLM_API.md"].decode("utf-8")
    tasks = json.loads(files[".vscode/tasks.json"])

    # onboard.md is a thin router — asks which mode (A = agent, B = llm-api)
    assert "which mode" in onboard.lower()
    # mode-specific details live in sub-files
    assert "llm provider" in onboard_llm.lower()
    assert "profile photo" in onboard_agent.lower() or "profile photo" in onboard_llm.lower()
    # Check for the provider/tool names the setup guide links out to, rather than
    # domain-shaped substrings (which read as URL-sanitization checks to static
    # analysis even though this is just "does the doc mention this tool").
    assert "python" in setup.lower() and "downloads" in setup.lower()
    assert "command not found" in setup.lower()
    assert "auto-approve" in setup_agent.lower()
    assert "openai" in setup_llm_api.lower() and "api-keys" in setup_llm_api.lower()
    assert "anthropic" in setup_llm_api.lower()
    assert tasks["tasks"][0]["command"] == "docker"
    assert "pdflatex" in tasks["tasks"][0]["args"]


def test_project_readme_links_setup_guide() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "[SETUP.md](job_hunter/templates/workspace/SETUP.md)" in readme


def test_workspace_updates_doc_uses_real_manifest_path() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = (root / "docs" / "workspace-updates.md").read_text(encoding="utf-8")
    assert MANIFEST_PATH in doc
    assert ".job-hunter-manifest.json" not in doc


def test_workspace_updates_doc_does_not_overclaim_manifest_scope() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = (root / "docs" / "workspace-updates.md").read_text(encoding="utf-8")
    assert "skill files only" in doc


def test_architecture_doc_does_not_underclaim_remaining_dict_usage() -> None:
    """docs/architecture.md must match models.py: dicts remain at pipeline boundaries too, not just serialization."""
    root = Path(__file__).resolve().parents[1]
    doc = (root / "docs" / "architecture.md").read_text(encoding="utf-8")
    assert "legacy pipeline boundaries" in doc
    assert "future cleanup" in doc


def test_init_creates_complete_workspace_from_package_template(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    run_init(workspace)

    assert (workspace / "config" / "job_hunter.yml").exists()
    assert not (workspace / "config" / "career_pages.yml").exists()
    assert not (workspace / "config" / "locations").exists()
    assert not (workspace / "config" / "location_data").exists()
    assert (workspace / ".github" / "workflows" / "find-jobs.yml").exists()
    assert (workspace / ".github" / "searxng" / "settings.yml").exists()
    assert (workspace / ".claude" / "skills" / "setup" / "SKILL.md").exists()
    assert (workspace / ".agents" / "skills" / "setup" / "SKILL.md").exists()
    assert (workspace / ".claude" / "settings.json").exists()
    assert (workspace / ".codex" / "hooks.json").exists()
    assert (workspace / "profile" / "resume_double_column.tex").exists()
    assert (workspace / "profile" / "resume_single_column.tex").exists()
    assert (workspace / "profile" / "career_context.md").exists()
    assert (workspace / "outputs" / "state" / "discovered_urls.yml").exists()
    assert not (workspace / "data").exists()
    assert not (workspace / "profile" / ".gitkeep").exists()
    setup = (workspace / "SETUP.md").read_text(encoding="utf-8")
    assert "Python 3.12 or 3.13" in setup
    assert "job-hunter doctor" in setup
    assert "job-hunter init" in setup
    assert "[SETUP_AGENT.md]" in setup
    assert "[SETUP_LLM_API.md]" in setup

    setup_agent = (workspace / "SETUP_AGENT.md").read_text(encoding="utf-8")
    assert "job-hunter hunt --region primary" in setup_agent
    assert "Auto mode scope" in setup_agent

    setup_llm_api = (workspace / "SETUP_LLM_API.md").read_text(encoding="utf-8")
    assert "GitHub Secrets" in setup_llm_api
    assert "Find Jobs" in setup_llm_api
    assert "Cost and token safety" in setup_llm_api

    # AGENTS.md/README.md must come from the user-workspace template, not the
    # product repo's own dev-facing copies — regression test for a bug where
    # _CANONICAL_FILES pulled root AGENTS.md/README.md into new workspaces
    # under an editable/source-checkout install.
    agents = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    readme = (workspace / "README.md").read_text(encoding="utf-8")
    assert "This is your personal Job Hunter workspace." in agents
    assert "agent context source of truth for the product repo" not in agents
    assert "Personal workspace for the `job-hunter` Python package" in readme
    assert "uv sync --extra dev" not in readme

    manifest = json.loads((workspace / MANIFEST_PATH).read_text(encoding="utf-8"))
    assert ".claude/skills/setup/SKILL.md" in manifest["managed_files"]
    assert "config/job_hunter.yml" not in manifest["managed_files"]
    assert "outputs/state/discovered_urls.yml" not in manifest["managed_files"]
    assert "data/.gitkeep" not in manifest["managed_files"]


def test_run_init_raises_on_non_empty_dir_without_force(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "existing.txt").write_text("data\n", encoding="utf-8")

    with pytest.raises(WorkspaceNotEmptyError):
        run_init(workspace)

    assert (workspace / "existing.txt").read_text(encoding="utf-8") == "data\n"
    assert not (workspace / MANIFEST_PATH).exists()


def test_run_init_force_reinitializes_and_reports_it(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "existing.txt").write_text("data\n", encoding="utf-8")

    result = run_init(workspace, force=True)

    assert result.reinitialized is True
    assert result.workspace == workspace.resolve()
    assert (workspace / MANIFEST_PATH).exists()


def test_workspace_operations_is_a_plain_service_layer() -> None:
    """operations.py must not import typer — presentation lives in cli/commands/update.py."""
    import inspect

    source = inspect.getsource(workspace_ops)
    assert "typer" not in source


@pytest.mark.parametrize(
    ("setup_result", "expected"),
    [
        (
            "conflict",
            ["Existing Codex OTel config preserved; Job Hunter token telemetry is not enabled for Codex."],
        ),
        (
            "invalid",
            ["Invalid Codex config preserved; Job Hunter token telemetry is not enabled for Codex."],
        ),
        ("configured", []),
    ],
)
def test_install_telemetry_returns_presentation_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    setup_result: str,
    expected: list[str],
) -> None:
    monkeypatch.setattr(
        "job_hunter.metrics.setup.install_workspace_telemetry",
        lambda _workspace: None,
    )
    monkeypatch.setattr(
        "job_hunter.metrics.setup.configure_codex_telemetry",
        lambda _path: setup_result,
    )

    assert workspace_ops.install_telemetry(tmp_path) == expected


def test_install_telemetry_failure_never_blocks_workspace_init(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "job_hunter.metrics.setup.install_workspace_telemetry",
        lambda _workspace: (_ for _ in ()).throw(PermissionError("private path")),
    )

    warnings = workspace_ops.install_telemetry(tmp_path)

    assert warnings == ["Telemetry setup could not be completed; run `job-hunter update` to retry."]


def test_update_skills_writes_only_skill_files_and_preserves_user_data(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    run_init(workspace)
    config = workspace / "config" / "job_hunter.yml"
    output = workspace / "outputs" / "state" / "discovered_urls.yml"
    custom_skill = workspace / ".claude" / "skills" / "custom" / "SKILL.md"
    config.write_text("user config stays\n", encoding="utf-8")
    output.write_text("user output stays\n", encoding="utf-8")
    custom_skill.parent.mkdir(parents=True)
    custom_skill.write_text("custom skill stays\n", encoding="utf-8")
    bundled_skill = workspace / ".claude" / "skills" / "setup" / "SKILL.md"
    bundled_skill.write_text("old bundled skill\n", encoding="utf-8")

    result = update_skills(workspace)

    assert result.written
    skill_prefixes = (".claude/skills/", ".agents/skills/", ".gemini/skills/")
    assert all(any(path.startswith(p) for p in skill_prefixes) for path in result.written)
    assert config.read_text(encoding="utf-8") == "user config stays\n"
    assert output.read_text(encoding="utf-8") == "user output stays\n"
    assert custom_skill.read_text(encoding="utf-8") == "custom skill stays\n"
    assert bundled_skill.read_text(encoding="utf-8") != "old bundled skill\n"


def test_update_skills_removes_unchanged_stale_managed_skill(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    run_init(workspace)
    stale_rel = ".claude/skills/setup/SKILL.md"
    stale = workspace / stale_rel
    current = [(rel, content) for rel, content in iter_template_skill_files() if rel != stale_rel]
    monkeypatch.setattr(workspace_ops, "iter_template_skill_files", lambda: current)

    result = update_skills(workspace)

    manifest = json.loads((workspace / MANIFEST_PATH).read_text(encoding="utf-8"))
    assert not stale.exists()
    assert stale_rel not in manifest["managed_files"]
    assert stale_rel in result.removed_stale
    assert result.preserved_modified == []


def test_update_skills_preserves_modified_stale_managed_skill(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    run_init(workspace)
    stale_rel = ".claude/skills/setup/SKILL.md"
    stale = workspace / stale_rel
    stale.write_text("user customization\n", encoding="utf-8")
    current = [(rel, content) for rel, content in iter_template_skill_files() if rel != stale_rel]
    monkeypatch.setattr(workspace_ops, "iter_template_skill_files", lambda: current)

    result = update_skills(workspace)

    manifest = json.loads((workspace / MANIFEST_PATH).read_text(encoding="utf-8"))
    assert stale.read_text(encoding="utf-8") == "user customization\n"
    assert stale_rel not in manifest["managed_files"]
    assert stale_rel in result.preserved_modified
    assert stale_rel not in result.removed_stale


def test_template_skill_files_are_subset_of_workspace_assets() -> None:
    skill_paths = {path for path, _content in iter_template_skill_files()}
    skill_prefixes = (".claude/skills/", ".agents/skills/", ".gemini/skills/")

    assert skill_paths
    assert all(any(path.startswith(p) for p in skill_prefixes) for path in skill_paths)


def test_packaged_workspace_assets_match_canonical_sources() -> None:
    from job_hunter.workspace.assets import _DEV_SKILL_DIRS

    root = Path(__file__).resolve().parents[1]
    packaged = dict(iter_packaged_resource_files())

    for skill_file in sorted((root / ".claude" / "skills").rglob("*")):
        if not skill_file.is_file():
            continue
        skill_dir = skill_file.relative_to(root / ".claude" / "skills").parts[0]
        if skill_dir in _DEV_SKILL_DIRS:
            continue
        rel = skill_file.relative_to(root).as_posix()
        assert rel in packaged, f"packaged template missing skill file: {rel}"
        assert packaged[rel] == skill_file.read_bytes(), f"packaged skill drifted: {rel}"

    for profile_file in sorted((root / "job_hunter" / "templates" / "workspace" / "profile").glob("*")):
        if profile_file.is_file():
            rel = f"profile/{profile_file.name}"
            assert rel in packaged, f"packaged template missing profile asset: {rel}"


def test_asset_ownership_predicates_are_explicit() -> None:
    assert is_resource_only_file("README.md")
    assert is_resource_only_file(".github/workflows/find-jobs.yml")
    assert is_resource_only_file("config/job_hunter.yml")
    assert is_dev_only_skill(".claude/skills/commit/SKILL.md")
    assert not is_dev_only_skill(".claude/skills/job-hunter/SKILL.md")
    assert not is_dev_only_skill(".agents/skills/commit/SKILL.md")


def test_source_checkout_assets_use_canonical_and_resource_owners() -> None:
    root = Path(__file__).resolve().parents[1]
    source = dict(_iter_source_checkout_files(root))
    packaged = dict(iter_packaged_resource_files())

    assert source["README.md"] == packaged["README.md"]
    assert source["profile/story_bank.md"] == packaged["profile/story_bank.md"]
    assert ".claude/skills/commit/SKILL.md" not in source
    assert ".claude/skills/job-hunter/SKILL.md" in source


def test_packaged_workspace_context_is_user_workspace_focused() -> None:
    packaged = dict(iter_packaged_resource_files())
    agents = packaged["AGENTS.md"].decode("utf-8")
    claude = packaged["CLAUDE.md"].decode("utf-8")
    readme = packaged["README.md"].decode("utf-8")

    assert "This is your personal Job Hunter workspace." in agents
    assert "Product code lives in the `job-hunter` Python package" in agents
    assert "https://github.com/abdulrbasit/job-hunter" in readme
    assert "@./AGENTS.md" in claude
    assert "job_hunter/" not in agents
    assert "uv sync --extra dev" not in readme


def test_update_workspace_assets_overwrites_docs_but_not_existing_yaml_config(tmp_path: Path) -> None:
    from job_hunter.workspace.assets import update_workspace_assets

    setup = tmp_path / "SETUP.md"
    setup.write_text("stale setup\n", encoding="utf-8")

    written = update_workspace_assets(tmp_path)

    packaged = dict(iter_packaged_resource_files())
    assert setup.read_bytes() == packaged["SETUP.md"]
    assert written == [
        "README.md",
        "SETUP.md",
        "SETUP_AGENT.md",
        "SETUP_LLM_API.md",
        "config/schemas/job_hunter.schema.json",
    ]


def test_update_workspace_assets_refreshes_stale_config_schema(tmp_path: Path) -> None:
    """config/schemas/job_hunter.schema.json is documented everywhere (SETUP.md, doctor's
    error hints) as system-owned and 'replaced on every update' — it must actually be
    refreshed by update_workspace_assets(), not only written once at init time."""
    from job_hunter.workspace.assets import update_workspace_assets

    schema_path = tmp_path / "config" / "schemas" / "job_hunter.schema.json"
    schema_path.parent.mkdir(parents=True)
    schema_path.write_text('{"stale": true}', encoding="utf-8")

    written = update_workspace_assets(tmp_path)

    packaged = dict(iter_packaged_resource_files())
    assert schema_path.read_bytes() == packaged["config/schemas/job_hunter.schema.json"]
    assert "config/schemas/job_hunter.schema.json" in written


def test_update_workspace_assets_does_not_touch_job_hunter_yml(tmp_path: Path) -> None:
    """config/job_hunter.yml is fully user-owned; update must never rewrite it."""
    from job_hunter.workspace.assets import update_workspace_assets

    job_config = tmp_path / "config" / "job_hunter.yml"
    job_config.parent.mkdir(parents=True)
    original = "# my comment\nmode: agent\n"
    job_config.write_text(original, encoding="utf-8")

    written = update_workspace_assets(tmp_path)

    assert job_config.read_text(encoding="utf-8") == original
    assert "config/job_hunter.yml" not in written


def test_update_workspace_assets_appends_sqlite_ignores_without_overwriting_existing_rules(tmp_path: Path) -> None:
    from job_hunter.workspace.assets import update_workspace_assets

    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("# mine\ncustom.cache\n", encoding="utf-8")

    update_workspace_assets(tmp_path)
    updated = gitignore.read_text(encoding="utf-8")

    assert updated.startswith("# mine\ncustom.cache\n")
    assert updated.count("outputs/state/jobs.db-wal") == 1
    assert updated.count("outputs/state/jobs.db-shm") == 1
    assert updated.count("outputs/state/companies.db-wal") == 1
    assert updated.count("outputs/state/companies.db-shm") == 1
    assert sum(1 for line in updated.splitlines() if line == "outputs/state/companies.db") == 1


def test_update_workspace_assets_does_not_recreate_retired_career_pages_file(tmp_path: Path) -> None:
    from job_hunter.workspace.assets import update_workspace_assets

    written = update_workspace_assets(tmp_path)

    packaged = dict(iter_packaged_resource_files())
    assert (tmp_path / "SETUP.md").read_bytes() == packaged["SETUP.md"]
    assert not (tmp_path / "config" / "career_pages.yml").exists()
    assert not (tmp_path / "config" / "job_hunter.yml").exists()
    assert written == [
        "README.md",
        "SETUP.md",
        "SETUP_AGENT.md",
        "SETUP_LLM_API.md",
        "config/schemas/job_hunter.schema.json",
    ]


def test_update_workspace_assets_refreshes_docs_and_preserves_readme_stats(tmp_path: Path) -> None:
    from job_hunter.workspace.assets import update_workspace_assets

    readme = tmp_path / "README.md"
    readme.write_text(
        "Old docs\n\n"
        "<!-- JOBS_STATS_START -->\n**Application stats:** 1 job tracked.\n<!-- JOBS_STATS_END -->\n\n"
        "<!-- JOBS_TABLE_START -->\n| Date | Job | Location | Score | Files |\n"
        "|---|---|---|---|---|\n| 2026-06-24 | [PM @ Acme](https://example.com/job) | Berlin | 90 | [Files](outputs/jobs/acme/) |\n"
        "<!-- JOBS_TABLE_END -->\n",
        encoding="utf-8",
    )

    written = update_workspace_assets(tmp_path)
    updated = readme.read_text(encoding="utf-8")

    assert "Start at [SETUP.md](SETUP.md)" in updated
    assert "**Application stats:** 1 job tracked." in updated
    assert "[PM @ Acme](https://example.com/job)" in updated
    assert (tmp_path / "SETUP.md").exists()
    assert written == [
        "README.md",
        "SETUP.md",
        "SETUP_AGENT.md",
        "SETUP_LLM_API.md",
        "config/schemas/job_hunter.schema.json",
    ]


def test_init_configures_codex_telemetry_in_codex_home(tmp_path: Path, monkeypatch) -> None:
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    run_init(tmp_path / "workspace")
    first = (codex_home / "config.toml").read_text(encoding="utf-8")
    run_init(tmp_path / "second-workspace")

    assert (codex_home / "config.toml").read_text(encoding="utf-8") == first
    assert "127.0.0.1:4318" in first


def test_preserve_user_schedule_carries_active_cron_into_new_template() -> None:
    existing_text = (
        "on:\n"
        "  schedule:\n"
        '    - cron: "0 18 * * 0-4"\n'
        "  workflow_dispatch:\n"
        "    inputs:\n"
        "      region:\n"
        '        default: ""\n'
    )
    new_text = (
        "on:\n"
        "  # Uncomment and adjust the cron lines below to enable automatic scraping.\n"
        "  # schedule:\n"
        '  #   - cron: "0 18 * * 0-4"   # 20:00 Berlin (CEST) / 19:00 CET - Mon-Fri\n'
        "  workflow_dispatch:\n"
        "    inputs:\n"
        "      region:\n"
        '        default: ""\n'
    )

    result = workspace_ops._preserve_user_schedule(existing_text, new_text)

    assert "  # Uncomment" not in result
    assert '  schedule:\n    - cron: "0 18 * * 0-4"\n' in result
    assert "  workflow_dispatch:" in result


def test_preserve_user_schedule_leaves_new_text_untouched_when_no_active_cron() -> None:
    existing_text = 'on:\n  # schedule:\n  #   - cron: "0 18 * * 0-4"\n  workflow_dispatch:\n'
    new_text = "on:\n  # Uncomment...\n  # schedule:\n  workflow_dispatch:\n"

    result = workspace_ops._preserve_user_schedule(existing_text, new_text)

    assert result == new_text


def test_run_init_seeds_workflow_hashes_in_manifest(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    run_init(workspace)

    manifest = json.loads((workspace / MANIFEST_PATH).read_text(encoding="utf-8"))

    assert ".github/workflows/tailor-job.yml" in manifest["managed_files"]


def test_update_workflows_flags_customized_non_scheduled_workflow(tmp_path: Path) -> None:
    """tailor-job.yml has no schedule-merge logic — a local edit to it must be reported,
    not silently discarded, even though the file is still updated."""
    workspace = tmp_path / "workspace"
    run_init(workspace)
    tailor_job = workspace / ".github" / "workflows" / "tailor-job.yml"
    tailor_job.write_text(tailor_job.read_text(encoding="utf-8") + "\n# local note\n", encoding="utf-8")

    result = update_workflows(workspace)

    assert ".github/workflows/tailor-job.yml" in result.customized
    assert "# local note" not in tailor_job.read_text(encoding="utf-8")


def test_update_workflows_does_not_flag_unmodified_workflow(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    run_init(workspace)

    result = update_workflows(workspace)

    assert result.customized == []


def test_update_workflows_preserves_cron_without_flagging_find_jobs_as_customized(tmp_path: Path) -> None:
    """Enabling the schedule is the single most common, fully-supported customization to
    find-jobs.yml — it must not trigger the generic "you edited this" warning."""
    workspace = tmp_path / "workspace"
    run_init(workspace)
    find_jobs = workspace / ".github" / "workflows" / "find-jobs.yml"
    text = find_jobs.read_text(encoding="utf-8")
    text = text.replace(
        '  # schedule:\n  #   - cron: "0 18 * * 0-4"   # 20:00 Berlin (CEST) / 19:00 CET - Mon-Fri\n',
        '  schedule:\n    - cron: "0 18 * * 0-4"\n',
    )
    find_jobs.write_text(text, encoding="utf-8")

    result = update_workflows(workspace)

    assert '- cron: "0 18 * * 0-4"' in find_jobs.read_text(encoding="utf-8")
    assert ".github/workflows/find-jobs.yml" not in result.customized
