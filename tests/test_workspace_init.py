from __future__ import annotations

import json
from pathlib import Path

import yaml

from job_hunter.workspace import operations as workspace_ops
from job_hunter.workspace.assets import iter_managed_files, iter_packaged_resource_files
from job_hunter.workspace.manifest import MANIFEST_PATH
from job_hunter.workspace.operations import iter_template_skill_files, run_init, update_skills


def test_workspace_template_assets_include_config_and_hidden_dirs() -> None:
    paths = {path for path, _content in iter_managed_files()}

    assert "config/job_hunter.yml" in paths
    assert "config/career_pages.yml" in paths
    assert ".github/workflows/career-hunt.yml" in paths
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


def test_workspace_template_config_is_valid_yaml() -> None:
    files = dict(iter_managed_files())
    config = yaml.safe_load(files["config/job_hunter.yml"].decode("utf-8"))

    assert config["profile"]["resume_tex"] == "profile/resume_double_column.tex"
    assert "career_context" in config["profile"]
    assert config["job_titles"] == []
    assert config["exclusions"]["title_terms"] == []
    assert config["exclusions"]["languages"] == []
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
    assert "python.org/downloads" in setup
    assert "command not found" in setup.lower()
    assert "auto-approve" in setup_agent.lower()
    assert "platform.openai.com/api-keys" in setup_llm_api
    assert "console.anthropic.com" in setup_llm_api
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
    assert (workspace / "config" / "career_pages.yml").exists()
    assert (workspace / ".github" / "workflows" / "career-hunt.yml").exists()
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

    update_skills(workspace)

    manifest = json.loads((workspace / MANIFEST_PATH).read_text(encoding="utf-8"))
    assert not stale.exists()
    assert stale_rel not in manifest["managed_files"]


def test_update_skills_preserves_modified_stale_managed_skill(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    run_init(workspace)
    stale_rel = ".claude/skills/setup/SKILL.md"
    stale = workspace / stale_rel
    stale.write_text("user customization\n", encoding="utf-8")
    current = [(rel, content) for rel, content in iter_template_skill_files() if rel != stale_rel]
    monkeypatch.setattr(workspace_ops, "iter_template_skill_files", lambda: current)

    update_skills(workspace)

    manifest = json.loads((workspace / MANIFEST_PATH).read_text(encoding="utf-8"))
    assert stale.read_text(encoding="utf-8") == "user customization\n"
    assert stale_rel not in manifest["managed_files"]


def test_template_skill_files_are_subset_of_workspace_assets() -> None:
    skill_paths = {path for path, _content in iter_template_skill_files()}
    skill_prefixes = (".claude/skills/", ".agents/skills/", ".gemini/skills/")

    assert skill_paths
    assert all(any(path.startswith(p) for p in skill_prefixes) for path in skill_paths)


def test_packaged_workspace_assets_match_canonical_sources() -> None:
    from job_hunter.workspace.assets import _DEV_SKILL_DIRS

    root = Path(__file__).resolve().parents[1]
    packaged = dict(iter_packaged_resource_files())

    canonical_files = ("config/career_pages.yml",)
    for rel in canonical_files:
        assert packaged[rel] == (root / rel).read_bytes(), f"packaged workspace asset drifted: {rel}"

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
    companies = tmp_path / "config" / "career_pages.yml"
    setup.write_text("stale setup\n", encoding="utf-8")
    companies.parent.mkdir(parents=True)
    original_companies = "companies:\n  - name: User Company\n"
    companies.write_text(original_companies, encoding="utf-8")

    written = update_workspace_assets(tmp_path)

    packaged = dict(iter_packaged_resource_files())
    assert setup.read_bytes() == packaged["SETUP.md"]
    # existing YAML config is untouched, not merged
    assert companies.read_text(encoding="utf-8") == original_companies
    assert written == [
        "README.md",
        "SETUP.md",
        "SETUP_AGENT.md",
        "SETUP_LLM_API.md",
    ]


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


def test_update_workspace_assets_creates_missing_company_config(tmp_path: Path) -> None:
    from job_hunter.workspace.assets import update_workspace_assets

    written = update_workspace_assets(tmp_path)

    packaged = dict(iter_packaged_resource_files())
    assert (tmp_path / "SETUP.md").read_bytes() == packaged["SETUP.md"]
    assert (tmp_path / "config" / "career_pages.yml").read_bytes() == packaged["config/career_pages.yml"]
    assert not (tmp_path / "config" / "job_hunter.yml").exists()
    assert written == [
        "README.md",
        "SETUP.md",
        "SETUP_AGENT.md",
        "SETUP_LLM_API.md",
        "config/career_pages.yml",
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
        "config/career_pages.yml",
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
