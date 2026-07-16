from __future__ import annotations

from pathlib import Path

import yaml

from job_hunter.config.migrations import migrate_legacy_exclusions


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
    assert migrated["filters"]["excluded_companies"]["entries"] == [{"value": "Acme"}]
    assert migrated["filters"]["excluded_titles"]["entries"] == [{"value": "intern"}]
    assert migrated["filters"]["excluded_industries"]["entries"] == [{"value": "gambling"}]
    assert "german" in migrated["filters"]["languages"]["description"]
    assert (tmp_path / "outputs" / "state" / "config_backups" / "pre_filters_job_hunter.yml.bak").exists()


def test_migration_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "config" / "job_hunter.yml"
    path.parent.mkdir(parents=True)
    path.write_text("filters: {}\n", encoding="utf-8")

    assert not migrate_legacy_exclusions(tmp_path).migrated
    assert path.read_text(encoding="utf-8") == "filters: {}\n"
