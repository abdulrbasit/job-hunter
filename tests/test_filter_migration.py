from __future__ import annotations

from pathlib import Path

import yaml

from job_hunter.config.migrations import migrate_legacy_exclusions, migrate_workspace_filter_files


def test_migration_moves_legacy_exclusions_without_losing_values(tmp_path: Path) -> None:
    path = tmp_path / "config" / "job_hunter.yml"
    path.parent.mkdir(parents=True)
    path.write_text(
        yaml.safe_dump(
            {
                "mode": "agent",
                "exclusions": {
                    "companies": ["Acme"],
                    "title_terms": ["intern"],
                    "languages": ["german"],
                    "industries": ["gambling"],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = migrate_legacy_exclusions(tmp_path)
    migrated = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert result.migrated
    assert "exclusions" not in migrated
    assert migrated["filters"]["excluded_companies"] == ["Acme"]
    assert migrated["filters"]["excluded_titles"] == ["intern"]
    assert migrated["filters"]["excluded_industries"] == ["gambling"]
    assert "de" not in migrated["filters"]["hunt_languages"]
    assert (tmp_path / "outputs" / "state" / "config_backups" / "pre_filters_job_hunter.yml.bak").exists()


def test_migration_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "config" / "job_hunter.yml"
    path.parent.mkdir(parents=True)
    path.write_text("filters: {}\n", encoding="utf-8")

    assert not migrate_legacy_exclusions(tmp_path).migrated
    assert path.read_text(encoding="utf-8") == "filters: {}\n"


def test_workspace_filter_files_fold_into_single_config_then_are_removed(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    filters_dir = config_dir / "filters"
    schemas_dir = config_dir / "schemas"
    filters_dir.mkdir(parents=True)
    schemas_dir.mkdir()
    (config_dir / "job_hunter.yml").write_text(
        yaml.safe_dump({"mode": "agent", "filters": {"excluded_titles": ["intern"]}, "custom": "keep"}),
        encoding="utf-8",
    )
    (filters_dir / "excluded_companies.yml").write_text(
        yaml.safe_dump({"description": "Blocked", "entries": [{"value": "Acme"}]}), encoding="utf-8"
    )
    (filters_dir / "excluded_industries.yml").write_text(yaml.safe_dump(["aerospace_defense"]), encoding="utf-8")
    (schemas_dir / "filter.schema.json").write_text("{}", encoding="utf-8")

    result = migrate_workspace_filter_files(tmp_path)
    migrated = yaml.safe_load((config_dir / "job_hunter.yml").read_text(encoding="utf-8"))

    assert result.migrated
    assert migrated["filters"] == {
        "excluded_titles": ["intern"],
        "excluded_companies": ["Acme"],
        "excluded_industries": ["aerospace_defense"],
    }
    assert migrated["custom"] == "keep"
    assert not filters_dir.exists()
    assert not (schemas_dir / "filter.schema.json").exists()


def test_workspace_filter_file_cleanup_is_idempotent(tmp_path: Path) -> None:
    assert not migrate_workspace_filter_files(tmp_path).migrated
