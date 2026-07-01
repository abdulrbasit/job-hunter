from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from typer.testing import CliRunner

from job_hunter.cli.app import app
from job_hunter.workspace import bridge_migration as bm
from job_hunter.workspace.bridge_migration import BRIDGE_MIGRATION_ID, run_bridge_migration
from job_hunter.workspace.manifest import read_manifest
from job_hunter.workspace.operations import run_init

_STOCK_COMMANDS_MD = b"# Command Reference\n\nHow to invoke job-hunter skills.\n"
_STOCK_LINKEDIN_YML = b"name: LinkedIn Automation\non: workflow_dispatch\n"
_STOCK_COMPANIES_BROWSER = yaml.dump({"companies": []}).encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _patch_tables(monkeypatch) -> None:
    """Point the migration's known-hash tables at fixture content this test controls."""
    monkeypatch.setattr(
        bm,
        "_OBSOLETE_FILES",
        {
            "COMMANDS.md": frozenset({_sha256(_STOCK_COMMANDS_MD)}),
            ".github/workflows/linkedin.yml": frozenset({_sha256(_STOCK_LINKEDIN_YML)}),
        },
    )
    monkeypatch.setattr(bm, "_RENAMED_CONFIG_FILES", {"config/companies_browser.yml": "config/career_pages.yml"})
    monkeypatch.setattr(bm, "_RENAME_SOURCE_KNOWN_HASHES", frozenset({_sha256(_STOCK_COMPANIES_BROWSER)}))


def test_old_workspace_without_manifest_is_untouched(tmp_path: Path, monkeypatch) -> None:
    _patch_tables(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "COMMANDS.md").write_text("user's own file, never shipped by us\n", encoding="utf-8")

    result = run_bridge_migration(workspace)

    assert (workspace / "COMMANDS.md").exists()
    assert result.preserved == ["COMMANDS.md"]
    assert not result.removed


def test_dry_run_changes_nothing(tmp_path: Path, monkeypatch) -> None:
    _patch_tables(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    obsolete = workspace / "COMMANDS.md"
    obsolete.write_bytes(_STOCK_COMMANDS_MD)

    result = run_bridge_migration(workspace, dry_run=True)

    assert obsolete.exists()
    assert result.removed == ["COMMANDS.md"]
    assert result.dry_run is True


def test_obsolete_unchanged_file_is_deleted(tmp_path: Path, monkeypatch) -> None:
    _patch_tables(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    obsolete = workspace / "COMMANDS.md"
    obsolete.write_bytes(_STOCK_COMMANDS_MD)

    result = run_bridge_migration(workspace)

    assert not obsolete.exists()
    assert result.removed == ["COMMANDS.md"]


def test_obsolete_modified_file_is_preserved(tmp_path: Path, monkeypatch) -> None:
    _patch_tables(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    obsolete = workspace / "COMMANDS.md"
    obsolete.write_text("user's own notes, not the shipped file\n", encoding="utf-8")

    result = run_bridge_migration(workspace)

    assert obsolete.exists()
    assert obsolete.read_text(encoding="utf-8") == "user's own notes, not the shipped file\n"
    assert result.preserved == ["COMMANDS.md"]
    assert not result.removed


def test_obsolete_directory_file_removed_only_if_safe(tmp_path: Path, monkeypatch) -> None:
    _patch_tables(monkeypatch)
    workspace = tmp_path / "workspace"
    (workspace / ".github" / "workflows").mkdir(parents=True)
    unchanged = workspace / ".github" / "workflows" / "linkedin.yml"
    unchanged.write_bytes(_STOCK_LINKEDIN_YML)
    modified_commands = workspace / "COMMANDS.md"
    modified_commands.write_text("user customized this\n", encoding="utf-8")

    result = run_bridge_migration(workspace)

    assert not unchanged.exists()
    assert modified_commands.exists()
    assert ".github/workflows/linkedin.yml" in result.removed
    assert "COMMANDS.md" in result.preserved


def test_protected_paths_are_never_touched(tmp_path: Path, monkeypatch) -> None:
    _patch_tables(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "COMMANDS.md").write_bytes(_STOCK_COMMANDS_MD)
    monkeypatch.setattr(bm, "is_protected", lambda rel: rel == "COMMANDS.md")

    result = run_bridge_migration(workspace)

    assert (workspace / "COMMANDS.md").exists()
    assert not result.removed
    assert not result.preserved  # protected paths are skipped entirely, not even reported


def test_profile_outputs_env_untouched(tmp_path: Path, monkeypatch) -> None:
    _patch_tables(monkeypatch)
    workspace = tmp_path / "workspace"
    run_init(workspace)
    profile_file = workspace / "profile" / "career_context.md"
    outputs_file = workspace / "outputs" / "state" / "discovered_urls.yml"
    env_file = workspace / ".env"
    profile_before = profile_file.read_bytes()
    outputs_before = outputs_file.read_bytes()
    env_file.write_text("SECRET=abc\n", encoding="utf-8")

    run_bridge_migration(workspace)

    assert profile_file.read_bytes() == profile_before
    assert outputs_file.read_bytes() == outputs_before
    assert env_file.read_text(encoding="utf-8") == "SECRET=abc\n"


def test_renamed_config_migrates_user_companies_when_new_path_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_tables(monkeypatch)
    workspace = tmp_path / "workspace"
    old_path = workspace / "config" / "companies_browser.yml"
    old_path.parent.mkdir(parents=True)
    old_path.write_text(
        yaml.dump({"companies": [{"name": "Acme", "career_url": "https://acme.example/jobs", "location": ""}]}),
        encoding="utf-8",
    )

    result = run_bridge_migration(workspace)

    new_path = workspace / "config" / "career_pages.yml"
    assert not old_path.exists()
    assert new_path.exists()
    assert yaml.safe_load(new_path.read_bytes())["companies"] == [
        {"name": "Acme", "career_url": "https://acme.example/jobs", "location": ""}
    ]
    assert ("config/companies_browser.yml", "config/career_pages.yml") in result.renamed


def test_renamed_config_preserves_old_when_new_already_has_user_data(tmp_path: Path, monkeypatch) -> None:
    _patch_tables(monkeypatch)
    workspace = tmp_path / "workspace"
    old_path = workspace / "config" / "companies_browser.yml"
    new_path = workspace / "config" / "career_pages.yml"
    old_path.parent.mkdir(parents=True)
    old_path.write_text(
        yaml.dump({"companies": [{"name": "Legacy Co", "career_url": "https://legacy.example", "location": ""}]}),
        encoding="utf-8",
    )
    new_path.write_text(
        yaml.dump({"companies": [{"name": "New Co", "career_url": "https://new.example", "location": ""}]}),
        encoding="utf-8",
    )

    result = run_bridge_migration(workspace)

    assert old_path.exists()  # old had real (non-stock) content — preserved, not deleted
    assert yaml.safe_load(new_path.read_bytes())["companies"] == [
        {"name": "New Co", "career_url": "https://new.example", "location": ""}
    ]
    assert "config/companies_browser.yml" in result.preserved


def test_renamed_config_removes_old_stock_content_when_new_already_exists(tmp_path: Path, monkeypatch) -> None:
    _patch_tables(monkeypatch)
    workspace = tmp_path / "workspace"
    old_path = workspace / "config" / "companies_browser.yml"
    new_path = workspace / "config" / "career_pages.yml"
    old_path.parent.mkdir(parents=True)
    old_path.write_bytes(_STOCK_COMPANIES_BROWSER)
    new_path.write_text(yaml.dump({"companies": []}), encoding="utf-8")

    result = run_bridge_migration(workspace)

    assert not old_path.exists()
    assert "config/companies_browser.yml" in result.removed


def test_migration_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    _patch_tables(monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "COMMANDS.md").write_bytes(_STOCK_COMMANDS_MD)

    first = run_bridge_migration(workspace)
    second = run_bridge_migration(workspace)

    assert first.removed == ["COMMANDS.md"]
    assert second.removed == []
    assert second.preserved == []


def test_running_migration_again_does_not_delete_more_files(tmp_path: Path, monkeypatch) -> None:
    _patch_tables(monkeypatch)
    workspace = tmp_path / "workspace"
    run_init(workspace)
    custom_file = workspace / "profile" / "my_notes.md"
    custom_file.write_text("keep me\n", encoding="utf-8")

    run_bridge_migration(workspace)
    run_bridge_migration(workspace)

    assert custom_file.read_text(encoding="utf-8") == "keep me\n"


def test_migration_id_is_recorded_after_full_update(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    workspace = tmp_path / "workspace"
    run_init(workspace)

    runner = CliRunner()
    result = runner.invoke(app, ["update", "--workspace", str(workspace)])

    assert result.exit_code == 0, result.output
    manifest = read_manifest(workspace)
    assert BRIDGE_MIGRATION_ID in manifest.applied_migrations


def test_update_dry_run_writes_nothing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    workspace = tmp_path / "workspace"
    run_init(workspace)
    manifest_before = (workspace / ".job-hunter" / "manifest.json").read_bytes()

    runner = CliRunner()
    result = runner.invoke(app, ["update", "--workspace", str(workspace), "--dry-run"])

    assert result.exit_code == 0, result.output
    assert (workspace / ".job-hunter" / "manifest.json").read_bytes() == manifest_before
