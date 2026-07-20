"""Tests for job_hunter/config/resumes.py — multi-language base resume resolution."""

from __future__ import annotations

from pathlib import Path

import yaml

from job_hunter.config import service
from job_hunter.config.resumes import base_resume_spec, normalized_resumes, resume_spec_for

_MAP_PROFILE = {
    "story_bank": "profile/story_bank.md",
    "career_context": "profile/career_context.md",
    "resumes": {
        "en": {"resume_tex": "profile/resume.tex", "base": True},
        "de": {"resume_tex": "profile/resume_de.tex", "latex_class": "profile/altacv_de.cls"},
    },
}


def _valid_config(profile: dict) -> dict:
    return {
        "mode": "agent",
        "profile": profile,
        "job_titles": ["Product Manager"],
        "regions": {"berlin": {"enabled": True, "country": "DE", "location": "Berlin"}},
        "filters": {"hunt_languages": ["en", "de"], "experience_levels": ["mid"]},
        "scoring": {"min_fit_score": 70, "batch_size": 15},
        "llm": {"default_provider": "anthropic"},
    }


def test_shorthand_normalizes_to_english_base() -> None:
    base, specs = normalized_resumes(
        {"resume_tex": "profile/resume.tex", "latex_class": "profile/altacv.cls", "profile_image": "profile/p.png"}
    )

    assert base == "en"
    assert specs == {
        "en": {
            "resume_tex": "profile/resume.tex",
            "latex_class": "profile/altacv.cls",
            "profile_image": "profile/p.png",
        }
    }


def test_single_entry_map_is_implicitly_base() -> None:
    base, specs = normalized_resumes({"resumes": {"de": {"resume_tex": "profile/resume_de.tex"}}})

    assert base == "de"
    assert specs["de"]["resume_tex"] == "profile/resume_de.tex"


def test_multi_entry_map_uses_the_marked_base() -> None:
    base, specs = normalized_resumes(_MAP_PROFILE)

    assert base == "en"
    assert set(specs) == {"en", "de"}
    assert base_resume_spec(_MAP_PROFILE)["resume_tex"] == "profile/resume.tex"


def test_resume_spec_for_prefers_target_language_and_falls_back_to_base() -> None:
    lang, spec = resume_spec_for(_MAP_PROFILE, "de")
    assert (lang, spec["resume_tex"]) == ("de", "profile/resume_de.tex")

    lang, spec = resume_spec_for(_MAP_PROFILE, "fr")
    assert (lang, spec["resume_tex"]) == ("en", "profile/resume.tex")


def test_validate_accepts_map_form_and_shorthand() -> None:
    root = Path("unused")
    shorthand = _valid_config(
        {
            "resume_tex": "profile/resume.tex",
            "story_bank": "profile/story_bank.md",
            "career_context": "profile/career_context.md",
        }
    )
    assert service.validate_job_hunter_yaml(shorthand, root) == []
    assert service.validate_job_hunter_yaml(_valid_config(_MAP_PROFILE), root) == []


def test_validate_rejects_shorthand_and_map_together() -> None:
    profile = {**_MAP_PROFILE, "resume_tex": "profile/resume.tex"}

    errors = service.validate_job_hunter_yaml(_valid_config(profile), Path("unused"))

    assert any("resume_tex" in e and "resumes" in e for e in errors)


def test_validate_requires_exactly_one_base_in_multi_entry_map() -> None:
    no_base = {
        **_MAP_PROFILE,
        "resumes": {
            "en": {"resume_tex": "profile/resume.tex"},
            "de": {"resume_tex": "profile/resume_de.tex"},
        },
    }
    two_base = {
        **_MAP_PROFILE,
        "resumes": {
            "en": {"resume_tex": "profile/resume.tex", "base": True},
            "de": {"resume_tex": "profile/resume_de.tex", "base": True},
        },
    }

    assert any("base" in e for e in service.validate_job_hunter_yaml(_valid_config(no_base), Path("unused")))
    assert any("base" in e for e in service.validate_job_hunter_yaml(_valid_config(two_base), Path("unused")))


def test_profile_path_resolves_base_entry_under_map_form(monkeypatch) -> None:
    import job_hunter.config.loader as loader
    from job_hunter.config.paths import profile_path

    monkeypatch.setattr(loader, "get_job_hunter_config", lambda: {"profile": _MAP_PROFILE})

    assert profile_path("resume_tex", "unused-default").name == "resume.tex"
    assert profile_path("story_bank", "profile/story_bank.md").name == "story_bank.md"


def test_profile_path_never_resolves_an_unset_empty_default_to_root(monkeypatch) -> None:
    """Regression: profile_path("profile_image", "") with no configured image used to
    resolve to ROOT itself (Path("") joined onto ROOT collapses to ROOT), so callers
    doing `if path.exists(): shutil.copy2(path, ...)` tried to copy the workspace root
    directory and crashed with PermissionError/IsADirectoryError."""
    import job_hunter.config.loader as loader
    from job_hunter.config.paths import ROOT, profile_path

    monkeypatch.setattr(loader, "get_job_hunter_config", lambda: {"profile": {"resume_tex": "resume.tex"}})

    path = profile_path("profile_image", "")

    assert path.name == ""
    assert path != ROOT
    assert not path.is_file()


def test_resume_tex_rel_resolves_base_entry(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "job_hunter.yml").write_text(yaml.safe_dump(_valid_config(_MAP_PROFILE)), encoding="utf-8")

    assert service._resume_tex_rel(tmp_path) == Path("profile/resume.tex")


def test_config_to_form_projects_base_entry_and_language_coverage() -> None:
    form = service.config_to_form(_valid_config(_MAP_PROFILE))

    assert form["profile"]["resume_tex"] == "profile/resume.tex"
    assert form["profile"]["latex_class"] == ""
    assert form["profile"]["resume_languages"] == ["de", "en"]
    assert form["profile"]["resume_base_lang"] == "en"


def test_apply_form_edits_base_entry_and_never_resurrects_shorthand() -> None:
    config = _valid_config(_MAP_PROFILE)
    form = service.config_to_form(config)
    form["profile"]["resume_tex"] = "profile/renamed.tex"
    form["profile"]["latex_class"] = "profile/altacv.cls"

    merged = service.apply_form_to_config(config, form)

    profile = merged["profile"]
    assert "resume_tex" not in profile
    assert "latex_class" not in profile
    assert profile["resumes"]["en"] == {
        "resume_tex": "profile/renamed.tex",
        "latex_class": "profile/altacv.cls",
        "base": True,
    }
    assert profile["resumes"]["de"]["resume_tex"] == "profile/resume_de.tex"  # untouched
    assert service.validate_job_hunter_yaml(merged, Path("unused")) == []
