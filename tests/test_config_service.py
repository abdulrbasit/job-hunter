"""Tests for config/service.py — safe read/validate/save/undo of user-editable config files."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from job_hunter.config import service

_VALID_CONFIG = {
    "mode": "agent",
    "profile": {
        "resume_tex": "profile/resume_double_column.tex",
        "story_bank": "profile/story_bank.md",
        "career_context": "profile/career_context.md",
    },
    "job_titles": ["Product Manager"],
    "regions": {"berlin": {"enabled": True, "country": "DE", "location": "Berlin"}},
    "filters": {},
    "scoring": {"min_fit_score": 70, "batch_size": 15},
    "llm": {"default_provider": "anthropic"},
}


def _write_config(root: Path, data: dict) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "job_hunter.yml").write_text(yaml.safe_dump(data), encoding="utf-8")


def _copy_schema(root: Path) -> None:
    schema_dir = root / "config" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    source_dir = Path(__file__).parents[1] / "config" / "schemas"
    for name in ("job_hunter.schema.json",):
        (schema_dir / name).write_text((source_dir / name).read_text(encoding="utf-8"), encoding="utf-8")


# ---------------------------------------------------------------------------
# Revisions
# ---------------------------------------------------------------------------


def test_get_revision_is_stable_for_same_bytes(tmp_path: Path) -> None:
    path = tmp_path / "f.yml"
    path.write_text("a: 1\n", encoding="utf-8")

    assert service.get_revision(path) == service.get_revision(path)


def test_get_revision_changes_when_bytes_change(tmp_path: Path) -> None:
    path = tmp_path / "f.yml"
    path.write_text("a: 1\n", encoding="utf-8")
    before = service.get_revision(path)
    path.write_text("a: 2\n", encoding="utf-8")

    assert service.get_revision(path) != before


def test_get_revision_of_missing_file_is_deterministic(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yml"

    assert service.get_revision(missing) == service.get_revision(tmp_path / "also-missing.yml")


# ---------------------------------------------------------------------------
# job_hunter.yml validation
# ---------------------------------------------------------------------------


def test_validate_job_hunter_yaml_accepts_valid_config(tmp_path: Path) -> None:
    _copy_schema(tmp_path)

    assert service.validate_job_hunter_yaml(_VALID_CONFIG, tmp_path) == []


def test_validate_job_hunter_yaml_accepts_linkedin_enabled_block(tmp_path: Path) -> None:
    """Regression: the schema never declared `linkedin` as an allowed top-level key,
    even though it's fully supported (LINKEDIN_DEFAULTS, linkedin_enabled(), and
    removed_keys.py's own enforcement all treat `linkedin: {enabled: bool}` as current,
    not removed) — any real workspace using it failed `job-hunter doctor`'s schema check."""
    _copy_schema(tmp_path)
    data = {**_VALID_CONFIG, "linkedin": {"enabled": False}}

    assert service.validate_job_hunter_yaml(data, tmp_path) == []


def test_validate_job_hunter_yaml_rejects_removed_keys(tmp_path: Path) -> None:
    _copy_schema(tmp_path)
    data = dict(_VALID_CONFIG)
    data["about_me"] = "stale"

    errors = service.validate_job_hunter_yaml(data, tmp_path)

    assert any("about_me" in e for e in errors)


def test_validate_job_hunter_yaml_rejects_schema_violation(tmp_path: Path) -> None:
    _copy_schema(tmp_path)
    data = dict(_VALID_CONFIG)
    data["mode"] = "not-a-real-mode"

    errors = service.validate_job_hunter_yaml(data, tmp_path)

    assert errors


def test_validate_job_hunter_yaml_rejects_non_mapping(tmp_path: Path) -> None:
    assert service.validate_job_hunter_yaml(["not", "a", "mapping"], tmp_path) == ["config must be a YAML mapping"]


def test_validate_job_hunter_yaml_rejects_unknown_filter_type(tmp_path: Path) -> None:
    _copy_schema(tmp_path)
    data = {
        **_VALID_CONFIG,
        "filters": {"companies": ["Acme"]},
    }

    errors = service.validate_job_hunter_yaml(data, tmp_path)

    assert any("Unknown filter type" in error for error in errors)


def test_validate_job_hunter_yaml_binds_taxonomy_choices_to_package_catalogs(tmp_path: Path) -> None:
    _copy_schema(tmp_path)
    data = {
        **_VALID_CONFIG,
        "filters": {"excluded_industries": ["not_a_package_industry"], "hunt_languages": ["zz"]},
    }

    errors = service.validate_job_hunter_yaml(data, tmp_path)

    assert any("unknown package IDs" in error for error in errors)
    assert any("unknown ISO codes" in error for error in errors)


# ---------------------------------------------------------------------------
# job_hunter.yml read/save/undo
# ---------------------------------------------------------------------------


def test_read_job_hunter_config_returns_raw_text_and_revision(tmp_path: Path) -> None:
    _write_config(tmp_path, _VALID_CONFIG)

    result = service.read_job_hunter_config(tmp_path)

    assert result["ok"] is True
    assert "mode: agent" in result["data"]
    assert result["revision"] == service.get_revision(tmp_path / "config" / "job_hunter.yml")


def test_save_job_hunter_config_writes_valid_yaml(tmp_path: Path) -> None:
    _write_config(tmp_path, _VALID_CONFIG)
    _copy_schema(tmp_path)
    before = service.read_job_hunter_config(tmp_path)
    new_data = dict(_VALID_CONFIG)
    new_data["job_titles"] = ["Staff Engineer"]
    new_text = yaml.safe_dump(new_data)

    result = service.save_job_hunter_config(tmp_path, new_text, before["revision"])

    assert result["ok"] is True
    on_disk = yaml.safe_load((tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8"))
    assert on_disk["job_titles"] == ["Staff Engineer"]


def test_save_job_hunter_config_rejects_invalid_yaml_without_touching_disk(tmp_path: Path) -> None:
    _write_config(tmp_path, _VALID_CONFIG)
    _copy_schema(tmp_path)
    before_text = (tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8")
    revision = service.get_revision(tmp_path / "config" / "job_hunter.yml")

    result = service.save_job_hunter_config(tmp_path, "not: valid: yaml: [", revision)

    assert result["ok"] is False
    assert (tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8") == before_text


def test_save_job_hunter_config_rejects_schema_violation_without_touching_disk(tmp_path: Path) -> None:
    _write_config(tmp_path, _VALID_CONFIG)
    _copy_schema(tmp_path)
    before_text = (tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8")
    revision = service.get_revision(tmp_path / "config" / "job_hunter.yml")
    bad = dict(_VALID_CONFIG)
    bad["mode"] = "nonsense"

    result = service.save_job_hunter_config(tmp_path, yaml.safe_dump(bad), revision)

    assert result["ok"] is False
    assert result["errors"]
    assert (tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8") == before_text


def test_save_job_hunter_config_rejects_stale_revision(tmp_path: Path) -> None:
    _write_config(tmp_path, _VALID_CONFIG)
    _copy_schema(tmp_path)
    stale_revision = "0" * 64
    new_data = dict(_VALID_CONFIG)
    new_data["job_titles"] = ["Staff Engineer"]

    result = service.save_job_hunter_config(tmp_path, yaml.safe_dump(new_data), stale_revision)

    assert result["ok"] is False
    assert "changed on disk" in result["errors"][0]
    on_disk = yaml.safe_load((tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8"))
    assert on_disk["job_titles"] == _VALID_CONFIG["job_titles"]


def test_save_job_hunter_config_clears_cached_config(tmp_path: Path, monkeypatch) -> None:
    _write_config(tmp_path, _VALID_CONFIG)
    _copy_schema(tmp_path)
    monkeypatch.setattr("job_hunter.config.paths.ROOT", tmp_path)
    monkeypatch.setattr("job_hunter.config.loader.ROOT", tmp_path)
    from job_hunter.config.loader import get_job_hunter_config

    get_job_hunter_config.cache_clear()
    first = get_job_hunter_config()
    assert first["job_titles"] == ["Product Manager"]

    revision = service.get_revision(tmp_path / "config" / "job_hunter.yml")
    new_data = dict(_VALID_CONFIG)
    new_data["job_titles"] = ["Staff Engineer"]
    service.save_job_hunter_config(tmp_path, yaml.safe_dump(new_data), revision)

    second = get_job_hunter_config()
    assert second["job_titles"] == ["Staff Engineer"]
    get_job_hunter_config.cache_clear()


def test_undo_job_hunter_config_restores_exact_prior_bytes(tmp_path: Path) -> None:
    _write_config(tmp_path, _VALID_CONFIG)
    _copy_schema(tmp_path)
    original_text = (tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8")
    revision = service.get_revision(tmp_path / "config" / "job_hunter.yml")
    new_data = dict(_VALID_CONFIG)
    new_data["job_titles"] = ["Staff Engineer"]
    save_result = service.save_job_hunter_config(tmp_path, yaml.safe_dump(new_data), revision)
    assert save_result["ok"] is True

    undo_result = service.undo_last_save(tmp_path, "job_hunter_config")

    assert undo_result["ok"] is True
    assert (tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8") == original_text


def test_undo_is_only_one_level(tmp_path: Path) -> None:
    _write_config(tmp_path, _VALID_CONFIG)
    _copy_schema(tmp_path)
    revision = service.get_revision(tmp_path / "config" / "job_hunter.yml")
    new_data = dict(_VALID_CONFIG)
    new_data["job_titles"] = ["Staff Engineer"]
    service.save_job_hunter_config(tmp_path, yaml.safe_dump(new_data), revision)

    first_undo = service.undo_last_save(tmp_path, "job_hunter_config")
    second_undo = service.undo_last_save(tmp_path, "job_hunter_config")

    assert first_undo["ok"] is True
    assert second_undo["ok"] is False
    assert "No backup" in second_undo["errors"][0]


def test_undo_unknown_logical_name_returns_error(tmp_path: Path) -> None:
    result = service.undo_last_save(tmp_path, "not-a-real-file")

    assert result["ok"] is False


# ---------------------------------------------------------------------------
# companies.targets validation
# ---------------------------------------------------------------------------


def test_validate_company_targets_accepts_full_entry() -> None:
    data = [
        {"name": "Stripe", "url": "https://stripe.com/jobs", "country": "DE", "city": "Berlin", "industry": "finance"}
    ]

    assert service.validate_company_targets(data) == []


def test_validate_company_targets_requires_name_url_and_country() -> None:
    errors = service.validate_company_targets([{}])

    assert any("name" in e for e in errors)
    assert any("url" in e for e in errors)
    assert any("country" in e for e in errors)


def test_validate_company_targets_rejects_non_https_scheme() -> None:
    errors = service.validate_company_targets([{"name": "Evil", "url": "http://evil.example/careers", "country": "DE"}])

    assert any("https" in e for e in errors)


def test_validate_company_targets_rejects_duplicate_url_and_country() -> None:
    errors = service.validate_company_targets(
        [
            {"name": "Stripe", "url": "https://stripe.com/jobs/", "country": "DE"},
            {"name": "Stripe Careers", "url": "HTTPS://STRIPE.COM/jobs", "country": "DE"},
        ]
    )

    assert any("duplicate url" in e for e in errors)


def test_validate_company_targets_allows_same_url_in_different_countries() -> None:
    errors = service.validate_company_targets(
        [
            {"name": "Stripe DE", "url": "https://stripe.com/jobs", "country": "DE"},
            {"name": "Stripe US", "url": "https://stripe.com/jobs", "country": "US"},
        ]
    )

    assert errors == []


def test_validate_company_targets_rejects_non_boolean_enabled() -> None:
    errors = service.validate_company_targets(
        [{"name": "Stripe", "url": "https://stripe.com/jobs", "country": "DE", "enabled": "yes"}]
    )

    assert any("boolean" in e for e in errors)


def test_validate_company_targets_rejects_non_iso_country() -> None:
    errors = service.validate_company_targets([{"name": "Stripe", "url": "https://stripe.com/jobs", "country": "GER"}])

    assert any("ISO alpha-2" in e for e in errors)


# ---------------------------------------------------------------------------
# companies.targets read/save/undo (a section of config/job_hunter.yml)
# ---------------------------------------------------------------------------


def test_read_company_targets_returns_targets_and_revision(tmp_path: Path) -> None:
    data = {
        **_VALID_CONFIG,
        "companies": {"targets": [{"name": "Stripe", "url": "https://stripe.com/jobs", "country": "DE"}]},
    }
    _write_config(tmp_path, data)

    result = service.read_company_targets(tmp_path)

    assert result["ok"] is True
    assert result["data"]["targets"] == [{"name": "Stripe", "url": "https://stripe.com/jobs", "country": "DE"}]
    assert result["revision"] == service.get_revision(tmp_path / "config" / "job_hunter.yml")


def test_read_company_targets_returns_empty_list_when_absent(tmp_path: Path) -> None:
    _write_config(tmp_path, _VALID_CONFIG)

    result = service.read_company_targets(tmp_path)

    assert result["data"]["targets"] == []


def test_save_company_targets_writes_into_job_hunter_yaml(tmp_path: Path) -> None:
    _write_config(tmp_path, _VALID_CONFIG)
    _copy_schema(tmp_path)
    revision = service.get_revision(tmp_path / "config" / "job_hunter.yml")

    result = service.save_company_targets(
        tmp_path, [{"name": "Stripe", "url": "https://stripe.com/jobs", "country": "DE"}], revision
    )

    assert result["ok"] is True
    reloaded = yaml.safe_load((tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8"))
    assert reloaded["companies"]["targets"] == [{"name": "Stripe", "url": "https://stripe.com/jobs", "country": "DE"}]
    assert reloaded["job_titles"] == _VALID_CONFIG["job_titles"]  # rest of the file untouched


def test_save_company_targets_omits_enabled_when_true(tmp_path: Path) -> None:
    _write_config(tmp_path, _VALID_CONFIG)
    _copy_schema(tmp_path)
    revision = service.get_revision(tmp_path / "config" / "job_hunter.yml")

    service.save_company_targets(
        tmp_path, [{"name": "Stripe", "url": "https://stripe.com/jobs", "country": "DE", "enabled": True}], revision
    )

    reloaded = yaml.safe_load((tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8"))
    assert "enabled" not in reloaded["companies"]["targets"][0]


def test_save_company_targets_keeps_enabled_false(tmp_path: Path) -> None:
    _write_config(tmp_path, _VALID_CONFIG)
    _copy_schema(tmp_path)
    revision = service.get_revision(tmp_path / "config" / "job_hunter.yml")

    service.save_company_targets(
        tmp_path, [{"name": "Stripe", "url": "https://stripe.com/jobs", "country": "DE", "enabled": False}], revision
    )

    reloaded = yaml.safe_load((tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8"))
    assert reloaded["companies"]["targets"][0]["enabled"] is False


def test_save_company_targets_empty_list_omits_companies_key(tmp_path: Path) -> None:
    data = {
        **_VALID_CONFIG,
        "companies": {"targets": [{"name": "Stripe", "url": "https://stripe.com/jobs", "country": "DE"}]},
    }
    _write_config(tmp_path, data)
    _copy_schema(tmp_path)
    revision = service.get_revision(tmp_path / "config" / "job_hunter.yml")

    service.save_company_targets(tmp_path, [], revision)

    reloaded = yaml.safe_load((tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8"))
    assert "companies" not in reloaded


def test_save_company_targets_rejects_invalid_entries_without_touching_disk(tmp_path: Path) -> None:
    _write_config(tmp_path, _VALID_CONFIG)
    _copy_schema(tmp_path)
    before_text = (tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8")
    revision = service.get_revision(tmp_path / "config" / "job_hunter.yml")

    result = service.save_company_targets(tmp_path, [{"name": "", "url": "not-a-url", "country": ""}], revision)

    assert result["ok"] is False
    assert (tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8") == before_text


def test_save_company_targets_rejects_stale_revision(tmp_path: Path) -> None:
    _write_config(tmp_path, _VALID_CONFIG)
    _copy_schema(tmp_path)

    result = service.save_company_targets(
        tmp_path, [{"name": "Stripe", "url": "https://stripe.com/jobs", "country": "DE"}], "0" * 64
    )

    assert result["ok"] is False


def test_undo_company_targets_restores_exact_prior_bytes(tmp_path: Path) -> None:
    _write_config(tmp_path, _VALID_CONFIG)
    _copy_schema(tmp_path)
    before_text = (tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8")
    revision = service.get_revision(tmp_path / "config" / "job_hunter.yml")
    service.save_company_targets(
        tmp_path, [{"name": "Stripe", "url": "https://stripe.com/jobs", "country": "DE"}], revision
    )

    result = service.undo_last_save(tmp_path, "job_hunter_config")

    assert result["ok"] is True
    assert (tmp_path / "config" / "job_hunter.yml").read_text(encoding="utf-8") == before_text


# ---------------------------------------------------------------------------
# career_context.md read/save/undo
# ---------------------------------------------------------------------------


def test_read_career_context_returns_text_and_revision(tmp_path: Path) -> None:
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "career_context.md").write_text("## About Me\n", encoding="utf-8")

    result = service.read_career_context(tmp_path)

    assert result["data"] == "## About Me\n"
    assert result["revision"] == service.get_revision(tmp_path / "profile" / "career_context.md")


def test_save_career_context_writes_utf8_text(tmp_path: Path) -> None:
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "career_context.md").write_text("old", encoding="utf-8")
    revision = service.get_revision(tmp_path / "profile" / "career_context.md")

    result = service.save_career_context(tmp_path, "## Über mich\n- café", revision)

    assert result["ok"] is True
    assert (tmp_path / "profile" / "career_context.md").read_text(encoding="utf-8") == "## Über mich\n- café"


def test_save_career_context_rejects_nul_bytes(tmp_path: Path) -> None:
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "career_context.md").write_text("old", encoding="utf-8")
    revision = service.get_revision(tmp_path / "profile" / "career_context.md")

    result = service.save_career_context(tmp_path, "bad\x00text", revision)

    assert result["ok"] is False
    assert (tmp_path / "profile" / "career_context.md").read_text(encoding="utf-8") == "old"


def test_save_career_context_rejects_oversized_content(tmp_path: Path) -> None:
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "career_context.md").write_text("old", encoding="utf-8")
    revision = service.get_revision(tmp_path / "profile" / "career_context.md")

    result = service.save_career_context(tmp_path, "x" * (service.MAX_CAREER_CONTEXT_BYTES + 1), revision)

    assert result["ok"] is False


def test_save_career_context_rejects_stale_revision(tmp_path: Path) -> None:
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "career_context.md").write_text("old", encoding="utf-8")

    result = service.save_career_context(tmp_path, "new", "0" * 64)

    assert result["ok"] is False
    assert (tmp_path / "profile" / "career_context.md").read_text(encoding="utf-8") == "old"


def test_undo_career_context_restores_exact_prior_bytes(tmp_path: Path) -> None:
    (tmp_path / "profile").mkdir()
    (tmp_path / "profile" / "career_context.md").write_text("original", encoding="utf-8")
    revision = service.get_revision(tmp_path / "profile" / "career_context.md")
    service.save_career_context(tmp_path, "changed", revision)

    result = service.undo_last_save(tmp_path, "career_context")

    assert result["ok"] is True
    assert (tmp_path / "profile" / "career_context.md").read_text(encoding="utf-8") == "original"


def test_career_context_honors_configured_profile_path(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text(
        yaml.safe_dump({"profile": {"career_context": "docs/context.md"}}), encoding="utf-8"
    )
    (tmp_path / "docs" / "context.md").write_text("custom location", encoding="utf-8")

    read = service.read_career_context(tmp_path)
    assert read["data"] == "custom location"

    result = service.save_career_context(tmp_path, "updated text", read["revision"])
    assert result["ok"] is True
    assert (tmp_path / "docs" / "context.md").read_text(encoding="utf-8") == "updated text"

    undo = service.undo_last_save(tmp_path, "career_context")
    assert undo["ok"] is True
    assert (tmp_path / "docs" / "context.md").read_text(encoding="utf-8") == "custom location"


# ---------------------------------------------------------------------------
# Onboarding: compact search-setup prefs (Phase 3)
# ---------------------------------------------------------------------------

_ONBOARDING_BASE_CONFIG = {
    "mode": "agent",
    "job_titles": ["Old Title"],
    "regions": {"primary": {"enabled": True, "country": "DE", "location": "Berlin"}},
    "filters": {"excluded_titles": ["intern"]},
    "scoring": {"min_fit_score": 70, "batch_size": 15},
}


def test_apply_onboarding_prefs_updates_titles_stage_and_primary_region() -> None:
    prefs = {
        "career_stage": "leadership",
        "job_titles": ["Director of Product"],
        "country": "us",
        "location": "New York",
        "search_lang": "en",
    }

    merged = service.apply_onboarding_prefs(_ONBOARDING_BASE_CONFIG, prefs)

    assert merged["career_stage"] == "leadership"
    assert merged["job_titles"] == ["Director of Product"]
    assert merged["regions"]["primary"]["country"] == "US"
    assert merged["regions"]["primary"]["scope"] == "city"
    assert merged["regions"]["primary"]["city_id"] == "geonames:5128581"
    assert "location" not in merged["regions"]["primary"]
    assert merged["regions"]["primary"]["search_lang"] == "en"


def test_apply_onboarding_prefs_leaves_scoring_and_other_filters_untouched() -> None:
    prefs = {"job_titles": ["New Title"]}

    merged = service.apply_onboarding_prefs(_ONBOARDING_BASE_CONFIG, prefs)

    assert merged["scoring"] == _ONBOARDING_BASE_CONFIG["scoring"]
    assert merged["filters"]["excluded_titles"] == ["intern"]


def test_apply_onboarding_prefs_sets_excluded_industries() -> None:
    prefs = {"job_titles": ["PM"], "excluded_industries": ["finance", "retail_ecommerce"]}

    merged = service.apply_onboarding_prefs(_ONBOARDING_BASE_CONFIG, prefs)

    assert merged["filters"]["excluded_industries"] == ["finance", "retail_ecommerce"]
    assert merged["filters"]["excluded_titles"] == ["intern"]


def test_apply_onboarding_prefs_preserves_other_regions() -> None:
    config = dict(_ONBOARDING_BASE_CONFIG)
    config["regions"] = {
        "primary": {"enabled": True, "country": "DE", "location": "Berlin"},
        "secondary": {"enabled": True, "country": "FR", "location": "Paris"},
    }
    prefs = {"job_titles": ["PM"], "country": "GB", "location": "London"}

    merged = service.apply_onboarding_prefs(config, prefs)

    assert merged["regions"]["secondary"] == {"enabled": True, "country": "FR", "location": "Paris"}
    assert merged["regions"]["primary"]["country"] == "GB"


# ---------------------------------------------------------------------------
# Onboarding: any-chatbot bundle import (Phase 3)
# ---------------------------------------------------------------------------


def _bootstrap_profile_dir(root: Path) -> None:
    (root / "profile").mkdir(parents=True, exist_ok=True)


def test_replace_onboarding_bundle_writes_all_three_files(tmp_path: Path) -> None:
    _bootstrap_profile_dir(tmp_path)
    sections = {
        "CAREER_CONTEXT": "- targeting: Product roles in Berlin",
        "STORY_BANK": "### Led a launch\nSTAR content here.",
        "BASE_RESUME": "# Jane Doe\nProduct Manager.",
    }

    result = service.replace_onboarding_bundle(tmp_path, sections)

    assert result["ok"] is True
    assert (tmp_path / "profile" / "career_context.md").read_text(encoding="utf-8") == sections["CAREER_CONTEXT"]
    assert (tmp_path / "profile" / "story_bank.md").read_text(encoding="utf-8") == sections["STORY_BANK"]
    assert (tmp_path / "profile" / "resume_source.md").read_text(encoding="utf-8") == sections["BASE_RESUME"]


def test_replace_onboarding_bundle_rejects_missing_section(tmp_path: Path) -> None:
    _bootstrap_profile_dir(tmp_path)

    result = service.replace_onboarding_bundle(tmp_path, {"CAREER_CONTEXT": "context", "STORY_BANK": "stories"})

    assert result["ok"] is False
    assert not (tmp_path / "profile" / "career_context.md").exists()


def test_replace_onboarding_bundle_backs_up_previous_content(tmp_path: Path) -> None:
    _bootstrap_profile_dir(tmp_path)
    (tmp_path / "profile" / "career_context.md").write_text("old context", encoding="utf-8")
    sections = {
        "CAREER_CONTEXT": "- targeting: new",
        "STORY_BANK": "new stories",
        "BASE_RESUME": "new resume",
    }

    service.replace_onboarding_bundle(tmp_path, sections)
    undo = service.undo_last_save(tmp_path, "career_context")

    assert undo["ok"] is True
    assert (tmp_path / "profile" / "career_context.md").read_text(encoding="utf-8") == "old context"


def test_replace_onboarding_bundle_rejects_invalid_career_context(tmp_path: Path) -> None:
    _bootstrap_profile_dir(tmp_path)
    sections = {
        "CAREER_CONTEXT": "has\x00nul",
        "STORY_BANK": "stories",
        "BASE_RESUME": "resume",
    }

    result = service.replace_onboarding_bundle(tmp_path, sections)

    assert result["ok"] is False
    assert not (tmp_path / "profile" / "story_bank.md").exists()


# ---------------------------------------------------------------------------
# Temp-file cleanup on failure
# ---------------------------------------------------------------------------


def test_atomic_write_cleans_up_temp_file_on_failure(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "target.yml"

    def boom(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(service.os, "replace", boom)

    with pytest.raises(OSError):
        service._atomic_write(path, b"content")

    leftover = list(tmp_path.glob(".target.yml.*.tmp"))
    assert leftover == []
    assert not path.exists()


# ---------------------------------------------------------------------------
# Guided form projection / merge
# ---------------------------------------------------------------------------

_FULL_CONFIG = {
    "mode": "agent",
    "profile": {
        "resume_tex": "profile/resume_double_column.tex",
        "story_bank": "profile/story_bank.md",
        "career_context": "profile/career_context.md",
        "latex_class": "altacv",
        "profile_image": "profile/photo.png",
    },
    "job_titles": ["Product Manager", "Staff PM"],
    "regions": {"berlin": {"enabled": True, "country": "DE", "location": "Berlin", "primary": True}},
    "filters": {"excluded_companies": ["Acme"], "excluded_titles": ["intern"]},
    "scoring": {
        "min_fit_score": 70,
        "max_years_experience_required": 10,
        "batch_size": 15,
        "strategic_overrides": [{"company": "Stripe", "min_score_override": 50}],
    },
    "llm": {
        "default_provider": "anthropic",
        "providers": {"scoring": "anthropic"},
        "models": {"scoring": "claude-haiku-4-5-20251001"},
        "max_tokens": {"scoring": 1000},
        "max_workers": 5,
        "rate_limits": {"anthropic": {"requests_per_minute": 50}},
        "ollama": {"base_url": "http://localhost:11434"},
    },
}


def test_config_to_form_projects_guided_fields() -> None:
    form = service.config_to_form(_FULL_CONFIG)

    assert form["mode"] == "agent"
    assert form["profile"]["resume_tex"] == "profile/resume_double_column.tex"
    assert form["profile"]["latex_class"] == "altacv"
    assert form["job_titles"] == ["Product Manager", "Staff PM"]
    assert form["regions"] == _FULL_CONFIG["regions"]
    assert form["filters"]["excluded_companies"] == ["Acme"]
    assert form["scoring"]["min_fit_score"] == 70
    assert form["scoring"]["strategic_overrides"] == [{"company": "Stripe", "min_score_override": 50}]
    assert form["llm_default_provider"] == "anthropic"
    assert "providers" not in form  # advanced-only llm fields are not in the guided form


def test_config_to_form_fills_blanks_for_missing_optional_fields() -> None:
    minimal = {"mode": "agent", "profile": {}, "job_titles": [], "regions": {}, "filters": {}, "scoring": {}}

    form = service.config_to_form(minimal)

    assert form["profile"]["latex_class"] == ""
    assert form["scoring"]["min_fit_score"] == 70
    assert form["scoring"]["max_years_experience_required"] is None
    assert form["scoring"]["strategic_overrides"] == []


def test_apply_form_to_config_preserves_advanced_llm_fields_untouched() -> None:
    form = service.config_to_form(_FULL_CONFIG)
    form["llm_default_provider"] = "openai"

    merged = service.apply_form_to_config(_FULL_CONFIG, form)

    assert merged["llm"]["default_provider"] == "openai"
    assert merged["llm"]["providers"] == {"scoring": "anthropic"}
    assert merged["llm"]["models"] == {"scoring": "claude-haiku-4-5-20251001"}
    assert merged["llm"]["max_tokens"] == {"scoring": 1000}
    assert merged["llm"]["max_workers"] == 5
    assert merged["llm"]["rate_limits"] == {"anthropic": {"requests_per_minute": 50}}
    assert merged["llm"]["ollama"] == {"base_url": "http://localhost:11434"}


def test_apply_form_to_config_round_trips_unchanged_form() -> None:
    form = service.config_to_form(_FULL_CONFIG)

    merged = service.apply_form_to_config(_FULL_CONFIG, form)

    assert merged == _FULL_CONFIG


def test_apply_form_to_config_updates_job_titles_and_strips_blanks() -> None:
    form = service.config_to_form(_FULL_CONFIG)
    form["job_titles"] = ["  Engineering Manager  ", "", "  "]

    merged = service.apply_form_to_config(_FULL_CONFIG, form)

    assert merged["job_titles"] == ["Engineering Manager"]


def test_apply_form_to_config_clears_optional_profile_field_when_blank() -> None:
    form = service.config_to_form(_FULL_CONFIG)
    form["profile"]["latex_class"] = ""

    merged = service.apply_form_to_config(_FULL_CONFIG, form)

    assert "latex_class" not in merged["profile"]


def test_apply_form_to_config_drops_strategic_overrides_missing_company() -> None:
    form = service.config_to_form(_FULL_CONFIG)
    form["scoring"]["strategic_overrides"] = [{"min_score_override": 50}]

    merged = service.apply_form_to_config(_FULL_CONFIG, form)

    assert "strategic_overrides" not in merged["scoring"]


def test_apply_form_to_config_produces_yaml_dumpable_result() -> None:
    form = service.config_to_form(_FULL_CONFIG)

    merged = service.apply_form_to_config(_FULL_CONFIG, form)

    yaml.safe_dump(merged)  # must not raise
