from __future__ import annotations

import json
from pathlib import Path

import yaml

from job_hunter.workspace._assets import iter_managed_files, iter_packaged_resource_files
from job_hunter.workspace.init import run_init
from job_hunter.workspace.manifest import MANIFEST_PATH
from job_hunter.workspace.skills import iter_template_skill_files, update_skills


def test_workspace_template_assets_include_config_and_hidden_dirs() -> None:
    paths = {path for path, _content in iter_managed_files()}

    assert "config/job_hunter.yml" in paths
    assert ".github/workflows/find-jobs.yml" in paths
    assert ".github/searxng/settings.yml" in paths
    assert ".claude/skills/setup/SKILL.md" in paths
    assert ".agents/skills/setup/SKILL.md" in paths
    assert ".gemini/skills/setup/SKILL.md" in paths
    assert ".env.example" in paths
    assert ".gitignore" in paths
    assert "outputs/state/discovered_urls.yml" in paths
    assert "data/.gitkeep" not in paths


def test_workspace_template_config_is_valid_yaml() -> None:
    files = dict(iter_managed_files())
    config = yaml.safe_load(files["config/job_hunter.yml"].decode("utf-8"))

    assert config["profile"]["resume_tex"] == "profile/resume_double_column.tex"
    assert "career_context" in config["profile"]
    assert "linkedin" not in config
    assert "tailoring" not in config
    assert "cover_letter" not in config


def test_init_creates_complete_workspace_from_package_template(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    run_init(workspace)

    assert (workspace / "config" / "job_hunter.yml").exists()
    assert (workspace / ".github" / "workflows" / "find-jobs.yml").exists()
    assert (workspace / ".github" / "searxng" / "settings.yml").exists()
    assert (workspace / ".claude" / "skills" / "setup" / "SKILL.md").exists()
    assert (workspace / ".agents" / "skills" / "setup" / "SKILL.md").exists()
    assert (workspace / ".gemini" / "skills" / "setup" / "SKILL.md").exists()
    assert (workspace / "profile" / "resume_double_column.tex").exists()
    assert (workspace / "profile" / "resume_single_column.tex").exists()
    assert (workspace / "profile" / "career_context.md").exists()
    assert (workspace / "outputs" / "state" / "discovered_urls.yml").exists()
    assert not (workspace / "data").exists()
    assert not (workspace / "profile" / ".gitkeep").exists()

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


def test_template_skill_files_are_subset_of_workspace_assets() -> None:
    skill_paths = {path for path, _content in iter_template_skill_files()}
    skill_prefixes = (".claude/skills/", ".agents/skills/", ".gemini/skills/")

    assert skill_paths
    assert all(any(path.startswith(p) for p in skill_prefixes) for path in skill_paths)


def test_packaged_workspace_assets_match_canonical_sources() -> None:
    from job_hunter.workspace._assets import _DEV_SKILL_DIRS

    root = Path(__file__).resolve().parents[1]
    packaged = dict(iter_packaged_resource_files())

    canonical_files = ("config/job_hunter.yml",)
    for rel in canonical_files:
        assert packaged[rel] == (root / rel).read_bytes(), f"packaged workspace asset drifted: {rel}"

    for skill in sorted((root / ".claude" / "skills").glob("*/SKILL.md")):
        if skill.parent.name in _DEV_SKILL_DIRS:
            continue
        rel = skill.relative_to(root).as_posix()
        assert packaged[rel] == skill.read_bytes(), f"packaged skill drifted: {rel}"

    for profile_file in sorted((root / "profile" / "template-files").glob("*")):
        if profile_file.is_file():
            rel = f"profile/{profile_file.name}"
            assert packaged[rel] == profile_file.read_bytes(), f"packaged profile asset drifted: {rel}"


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
