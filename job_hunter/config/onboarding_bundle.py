"""Any-chatbot onboarding: build a copyable setup prompt, parse a pasted response.

The prompt asks an external chatbot to return exactly three delimited sections
(CAREER_CONTEXT, STORY_BANK, BASE_RESUME). parse_onboarding_bundle validates all
three are present and non-empty before job_hunter.config.service.replace_onboarding_bundle
atomically stages and replaces the corresponding profile files — all or nothing.
"""

from __future__ import annotations

SECTIONS: tuple[str, ...] = ("CAREER_CONTEXT", "STORY_BANK", "BASE_RESUME")

MAX_BUNDLE_BYTES = 512 * 1024


def _start_delimiter(name: str) -> str:
    return f"<<<{name}>>>"


def _end_delimiter(name: str) -> str:
    return f"<<<END_{name}>>>"


def build_onboarding_prompt(config: dict) -> str:
    """A copyable prompt for any chatbot: paste this, get back a bundle to import."""
    job_titles = ", ".join(str(t) for t in (config.get("job_titles") or [])) or "(ask me for my target roles)"
    lines = [
        "You are helping me set up my job-search profile for the Job Hunter tool.",
        "Ask me about my work history, education, projects, coursework, volunteering,",
        f"and target roles (current target titles: {job_titles}). Work experience is",
        "not required — projects, coursework, and volunteering count as evidence too.",
        "Never invent employers, dates, or metrics I did not tell you.",
        "",
        "When you have enough information, reply with EXACTLY these three sections,",
        "each wrapped in its start/end markers below, and nothing else outside them:",
        "",
        _start_delimiter("CAREER_CONTEXT"),
        "(About-me notes, targeting, resume style, cover-letter style, outreach tone,",
        " and calibration notes, as plain text or markdown bullets.)",
        _end_delimiter("CAREER_CONTEXT"),
        "",
        _start_delimiter("STORY_BANK"),
        "(Reusable STAR-format stories: situation, task, action, result. Draw from work,",
        " projects, coursework, volunteering, clubs, or personal projects.)",
        _end_delimiter("STORY_BANK"),
        "",
        _start_delimiter("BASE_RESUME"),
        "(Full resume content as plain text or markdown: sections, bullets, dates.)",
        _end_delimiter("BASE_RESUME"),
        "",
    ]
    return "\n".join(lines)


def parse_onboarding_bundle(text: str) -> tuple[dict[str, str], list[str]]:
    """Extract and validate the three delimited sections from a pasted chatbot response.

    Returns (sections, errors). sections only contains keys that parsed successfully;
    callers must check errors is empty before trusting sections has all three keys.
    """
    if len(text.encode("utf-8")) > MAX_BUNDLE_BYTES:
        return {}, [f"Pasted bundle exceeds max size of {MAX_BUNDLE_BYTES} bytes"]

    sections: dict[str, str] = {}
    errors: list[str] = []
    for name in SECTIONS:
        start, end = _start_delimiter(name), _end_delimiter(name)
        start_idx = text.find(start)
        end_idx = text.find(end)
        if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
            errors.append(f"Missing or malformed {name} section (expected {start} ... {end})")
            continue
        content = text[start_idx + len(start) : end_idx].strip("\n").strip()
        if not content:
            errors.append(f"{name} section is empty")
            continue
        sections[name] = content
    return sections, errors
