"""Multi-language base resume resolution.

`profile.resume_tex` (string shorthand) means one English base resume.
`profile.resumes` maps language code → {resume_tex, latex_class?, profile_image?, base?}:
the entry marked `base: true` is the fallback source for every language without its
own base (a single-entry map is implicitly base). Values are returned raw — callers
apply their own defaults, exactly as they did for the flat profile keys.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SPEC_KEYS = ("resume_tex", "latex_class", "profile_image")


def normalized_resumes(profile: dict[str, Any]) -> tuple[str, dict[str, dict[str, str]]]:
    """(base_lang, {lang: spec}) for either config shape. Shorthand = English base."""
    resumes = profile.get("resumes")
    if isinstance(resumes, dict) and resumes:
        specs = {
            str(lang): {key: str(spec.get(key) or "") for key in SPEC_KEYS}
            for lang, spec in resumes.items()
            if isinstance(spec, dict)
        }
        base = next((str(lang) for lang, spec in resumes.items() if isinstance(spec, dict) and spec.get("base")), "")
        return (base or next(iter(specs), "en")), specs
    return "en", {"en": {key: str(profile.get(key) or "") for key in SPEC_KEYS}}


def base_resume_spec(profile: dict[str, Any]) -> dict[str, str]:
    base, specs = normalized_resumes(profile)
    return specs.get(base) or dict.fromkeys(SPEC_KEYS, "")


def resume_spec_for(profile: dict[str, Any], lang: str) -> tuple[str, dict[str, str]]:
    """(chosen_lang, spec): the target language's own base when present, else the base entry."""
    base, specs = normalized_resumes(profile)
    if lang in specs:
        return lang, specs[lang]
    return base, specs.get(base) or dict.fromkeys(SPEC_KEYS, "")


def resume_paths_for(lang: str = "") -> tuple[str, dict[str, Path]]:
    """Runtime path resolution for the resume serving `lang` (its own base or the fallback).

    Returns (chosen_lang, absolute paths). Defaults mirror the historical per-caller
    defaults: resume.tex / altacv.cls / empty profile image."""
    from job_hunter.config.loader import get_job_hunter_config
    from job_hunter.config.paths import ROOT

    profile = get_job_hunter_config().get("profile", {})
    chosen, spec = resume_spec_for(profile, lang)

    def _path(value: str, default: str) -> Path:
        path = Path(value or default)
        return path if path.is_absolute() else ROOT / path

    return chosen, {
        "resume_tex": _path(spec.get("resume_tex", ""), "resume.tex"),
        "latex_class": _path(spec.get("latex_class", ""), "altacv.cls"),
        "profile_image": _path(spec.get("profile_image", ""), ""),
    }


def validate_resumes(profile: dict[str, Any]) -> list[str]:
    """Structural rules JSON Schema can't express: shorthand xor map, exactly one base."""
    resumes = profile.get("resumes")
    if resumes is None:
        return []
    if profile.get("resume_tex"):
        return ["profile: use either resume_tex (shorthand) or the resumes map, not both"]
    if not isinstance(resumes, dict) or not resumes:
        return ["profile.resumes must be a non-empty mapping of language code to resume entry"]
    marked = [lang for lang, spec in resumes.items() if isinstance(spec, dict) and spec.get("base")]
    if len(resumes) > 1 and len(marked) != 1:
        return ["profile.resumes: mark exactly one entry with base: true"]
    return []
