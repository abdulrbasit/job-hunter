"""Deterministic output-language routing and the shared translate-and-tailor policy.

Both execution modes consume these: llm-api bakes the blocks into user prompts
(system prompts stay language-invariant for prompt caching), agent mode ships them
inside the tailor/outreach/interview context payloads. Pure functions — callers
pass config-derived values in; this module never reads config itself.
"""

from __future__ import annotations

from job_hunter.core.builtin_filters import LANG_CODE_TO_NAME


def resolve_output_language(job_lang: str | None, hunt_languages: list[str], base_lang: str) -> str:
    """Target output language: the detected posting language when hunted, else the base."""
    if job_lang and job_lang in hunt_languages:
        return job_lang
    return base_lang


def language_name(code: str) -> str:
    return LANG_CODE_TO_NAME.get(code, code).title() if code in LANG_CODE_TO_NAME else code


def artifact_suffix(lang: str) -> str:
    """Language segment for artifact filenames: resume_tailored.de.tex, cover_letter.en.md."""
    return f".{lang}" if lang else ""


def translation_rules(target: str) -> tuple[str, ...]:
    """Translate-and-tailor block for when no base resume exists in the target language.

    Phrased as a target-output-language directive (not "translate from X") so it stays
    correct whatever language the source resume happens to be in."""
    if not target:
        return ()
    name = language_name(target)
    return (
        f"Produce ALL output text in {name} — every section heading, bullet, and summary.",
        "Preserve the LaTeX commands, document structure, dates, and employer names exactly; "
        "translate only the human-readable text.",
        "Do not translate proper nouns, product names, certifications, or technical terms "
        f"that are conventionally written in English even in {name} business documents.",
        f"Write native, professional {name} — no literal word-for-word calques.",
    )


def cover_language_line(target: str) -> str:
    return f"Write the letter in {language_name(target)}."
