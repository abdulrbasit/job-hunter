from __future__ import annotations

from pathlib import Path

import yaml

from job_hunter.config.migrations import (
    migrate_career_pages,
    migrate_career_stage,
    migrate_legacy_exclusions,
    migrate_workspace_filter_files,
)


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


def test_migrate_career_pages_moves_custom_entries_into_targets(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "job_hunter.yml").write_text(
        yaml.safe_dump(
            {"mode": "agent", "regions": {"primary": {"enabled": True, "country": "DE", "scope": "country"}}}
        ),
        encoding="utf-8",
    )
    (config_dir / "career_pages.yml").write_text(
        yaml.safe_dump(
            {
                "companies": [
                    {"name": "Custom Co", "career_url": "https://custom.example/careers", "location": "Berlin"},
                    {"name": "No Location Co", "career_url": "https://noloc.example/careers", "enabled": False},
                ],
                "catalog": {"enabled_company_ids": ["sap"]},
            }
        ),
        encoding="utf-8",
    )

    result = migrate_career_pages(tmp_path)
    migrated = yaml.safe_load((config_dir / "job_hunter.yml").read_text(encoding="utf-8"))

    assert result.migrated
    targets = migrated["companies"]["targets"]
    assert {"name": "Custom Co", "url": "https://custom.example/careers", "country": "DE"} in targets
    no_loc = next(t for t in targets if t["name"] == "No Location Co")
    assert no_loc["country"] == "DE"  # falls back to the first enabled region's country
    assert no_loc["enabled"] is False
    assert not (config_dir / "career_pages.yml").exists()
    assert (tmp_path / "outputs" / "state" / "config_backups" / "career_pages.yml.bak").exists()


def test_migrate_career_pages_enables_store_rows_from_allowlist(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "job_hunter.yml").write_text(yaml.safe_dump({"mode": "agent"}), encoding="utf-8")
    (config_dir / "career_pages.yml").write_text(
        yaml.safe_dump({"companies": [], "catalog": {"enabled_company_ids": ["sap"]}}), encoding="utf-8"
    )

    migrate_career_pages(tmp_path)

    from job_hunter.companies import store

    rows = store.query_page(tmp_path, source="catalog", enabled=True)["items"]
    assert any(r["catalog_id"] == "sap" for r in rows)


def test_migrate_career_pages_is_idempotent(tmp_path: Path) -> None:
    assert not migrate_career_pages(tmp_path).migrated


def _write_career_stage_config(tmp_path: Path, career_stage: str) -> Path:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "job_hunter.yml"
    path.write_text(yaml.safe_dump({"mode": "agent", "career_stage": career_stage}), encoding="utf-8")
    return path


def test_migrate_career_stage_maps_each_named_stage(tmp_path: Path) -> None:
    expected = {
        "student": ["student_intern", "student_working_student", "student_thesis", "entry"],
        "early_career": ["entry", "junior"],
        "experienced": ["associate", "mid", "senior"],
        "leadership": ["lead", "staff", "principal", "manager", "director", "vp", "c_level"],
    }
    for stage, levels in expected.items():
        path = _write_career_stage_config(tmp_path, stage)

        result = migrate_career_stage(tmp_path)
        migrated = yaml.safe_load(path.read_text(encoding="utf-8"))

        assert result.migrated
        assert "career_stage" not in migrated
        assert migrated["filters"]["experience_levels"] == levels


def test_migrate_career_stage_custom_maps_to_all_levels(tmp_path: Path) -> None:
    from job_hunter.core.experience import load_experience_levels

    _write_career_stage_config(tmp_path, "custom")

    result = migrate_career_stage(tmp_path)
    migrated = yaml.safe_load((tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8"))

    assert result.migrated
    assert set(migrated["filters"]["experience_levels"]) == {level.id for level in load_experience_levels()}


def test_migrate_career_stage_writes_backup_once(tmp_path: Path) -> None:
    _write_career_stage_config(tmp_path, "experienced")

    migrate_career_stage(tmp_path)

    assert (tmp_path / "outputs" / "state" / "config_backups" / "pre_experience_levels_job_hunter.yml.bak").exists()


def test_migrate_career_stage_is_idempotent(tmp_path: Path) -> None:
    assert not migrate_career_stage(tmp_path).migrated
