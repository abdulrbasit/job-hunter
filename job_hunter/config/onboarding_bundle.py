"""Any-chatbot onboarding: copyable prompts + single-section reply parsing.

For users without a coding agent (Claude Code/Codex), each of the three profile
artifacts (career context, story bank, base resume) gets its own prompt that embeds
the current file content and asks a browser chatbot (ChatGPT, Claude.ai, etc.) to
return one complete replacement file, wrapped in a start/end delimiter pair.
parse_single_section extracts and validates that one section; callers always write
the result as a whole-file replacement, never a merge, since the prompt already
asked for the complete file back.
"""

from __future__ import annotations

MAX_BUNDLE_BYTES = 512 * 1024


def _start_delimiter(name: str) -> str:
    return f"<<<{name}>>>"


def _end_delimiter(name: str) -> str:
    return f"<<<END_{name}>>>"


def build_career_context_prompt(current_text: str) -> str:
    lines = [
        "You are helping me fill in my career-context file for the Job Hunter tool.",
        "This file has 9 fixed sections: About Me, Targeting, Resume Style, Cover",
        "Letter Style, LinkedIn Positioning, Outreach Tone, Interview Prep, Evidence",
        "Rules, and Calibration. Walk me through each section one at a time, asking",
        "focused questions, before moving to the next. Never invent details — only",
        "write what I tell you; leave a field blank if I don't know it. Evidence Rules",
        "matters most: ask explicitly what's safe to state versus what needs care, and",
        "what must never be mentioned.",
        "",
        "Here is my current file (template or partially filled) — keep the same",
        "section headers and structure, just fill in or update the content:",
        "",
        "```markdown",
        current_text,
        "```",
        "",
        "When we're done, reply with the complete replacement file wrapped in exactly",
        "these markers, and nothing else outside them:",
        "",
        _start_delimiter("CAREER_CONTEXT"),
        "(the full career_context.md content)",
        _end_delimiter("CAREER_CONTEXT"),
    ]
    return "\n".join(lines)


def build_story_bank_prompt(current_text: str) -> str:
    lines = [
        "You are helping me turn my raw work notes into STAR-format stories for the",
        "Job Hunter tool's story bank. Ask me for my work history, projects,",
        "coursework, or volunteering, one at a time, and turn each into a rated STAR",
        "story (Situation, Task, Action, Result) with honest feedback on how strong it",
        "is. Never invent employers, dates, titles, or metrics I did not tell you — if",
        "a story is weak, say so and keep it weak rather than embellishing it.",
        "",
        "Here is my current story bank file:",
        "",
        "```markdown",
        current_text,
        "```",
        "",
        "Place every story you draft under its role's '## Draft' heading — never",
        "under '## Final'. I'll review the drafts myself and promote the ones I like.",
        "",
        "When we're done, reply with the complete replacement file wrapped in exactly",
        "these markers, and nothing else outside them:",
        "",
        _start_delimiter("STORY_BANK"),
        "(the full story_bank.md content, with drafts added under Draft headings only)",
        _end_delimiter("STORY_BANK"),
    ]
    return "\n".join(lines)


def build_resume_prompt(resume_tex_text: str, career_context_text: str, story_bank_text: str) -> str:
    lines = [
        "You are helping me build my base resume for the Job Hunter tool. It's a",
        "LaTeX file — preserve every LaTeX command and the document structure exactly.",
        "Only replace placeholder text (e.g. Name, Title, Bullet point 1, city,",
        "country). Only use content I give you or that appears in the two files",
        "below — never invent facts, metrics, dates, or claims. Respect any character",
        "limits stated in the Resume Style section below.",
        "",
        "Ask me for anything missing (name, tagline, location, contact details)",
        "before you write the final version.",
        "",
        "My career context:",
        "",
        "```markdown",
        career_context_text,
        "```",
        "",
        "My story bank (use only the Final sections as approved bullets):",
        "",
        "```markdown",
        story_bank_text,
        "```",
        "",
        "My current resume template to fill in:",
        "",
        "```latex",
        resume_tex_text,
        "```",
        "",
        "When we're done, reply with the complete replacement .tex file wrapped in",
        "exactly these markers, and nothing else outside them:",
        "",
        _start_delimiter("BASE_RESUME"),
        "(the full populated .tex content)",
        _end_delimiter("BASE_RESUME"),
    ]
    return "\n".join(lines)


def parse_single_section(text: str, name: str) -> tuple[str | None, list[str]]:
    """Extract and validate one delimited section from a pasted chatbot reply."""
    if len(text.encode("utf-8")) > MAX_BUNDLE_BYTES:
        return None, [f"Pasted reply exceeds max size of {MAX_BUNDLE_BYTES} bytes"]

    start, end = _start_delimiter(name), _end_delimiter(name)
    start_idx = text.find(start)
    end_idx = text.find(end)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        return None, [f"Missing or malformed {name} section (expected {start} ... {end})"]

    content = text[start_idx + len(start) : end_idx].strip("\n").strip()
    if not content:
        return None, [f"{name} section is empty"]
    return content, []
