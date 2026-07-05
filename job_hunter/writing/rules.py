"""Universal writing rules — the single source of truth for safety, ATS
readability, and factual-accuracy constraints.

Both llm-api mode (system prompts in job_hunter/pipeline, job_hunter/llm/prompts)
and agent mode (agent_context payloads, .claude/skills/job-hunter) apply these
rules. User preferences in career_context.md may add style guidance but never
override these.
"""

from __future__ import annotations

EVIDENCE_RULES: tuple[str, ...] = (
    "Every claim must be directly supported by the base resume, selected final stories, "
    "career context, or job artifact evidence.",
    "Never infer, extrapolate, or combine claims across sources.",
    "If evidence is missing, omit rather than invent.",
)

RESUME_RULES: tuple[str, ...] = (
    "Never fabricate or modify employers, titles, dates, degrees, certifications, skills, "
    "tools, metrics, counts, percentages, outcomes, or scope.",
    "Mirror JD keywords only when naturally supported by existing experience. No keyword stuffing.",
    "Prefer action + scope + outcome bullets.",
    "Preserve LaTeX commands, document class, layout, employers, titles, and dates.",
    "Surgical edits only in agent mode; complete-file return only where llm-api mode already expects complete LaTeX.",
    *EVIDENCE_RULES,
)

ATS_RULES: tuple[str, ...] = (
    "Preserve ATS-readable structure: standard headings, simple text, no tables or graphics, "
    "no header-only critical content, unless already part of the LaTeX template.",
)

COVER_LETTER_RULES: tuple[str, ...] = (
    "Be concise and specific to the company, role, and job description.",
    "Use verified stories and facts only.",
    "No story IDs or bracketed citations.",
    "No markdown headers or bullet points unless the existing product format explicitly requires them.",
    'No generic AI filler such as "I am excited to apply" unless user style asks for it and the '
    "letter still stays specific.",
    'Focus on reader/company needs, not only "I want".',
    "Do not over-claim industry or domain expertise unless supported.",
    "Keep within the configured target/max word count and paragraph count.",
    *EVIDENCE_RULES,
)

OUTREACH_RULES: tuple[str, ...] = (
    "Draft only. Never send, connect, follow, like, or comment.",
    "Public web search only. No login or scraping of private data.",
    "Never invent contacts, titles, relationships, referrals, or claims.",
    "Keep messages short and specific.",
    "Ground fit claims in selected stories, the JD, or company research.",
    "Include a clear, low-friction ask.",
    "If no real person is found, write a generic recruiter/team outreach draft and say no verified profile was found.",
)

SCORE_DECISION_RULES: tuple[str, ...] = (
    "APPLY only when score meets the live min_fit_score threshold, or a matching strategic override applies.",
    "strategic_overrides[].bypass_max_years_experience == true skips the years-of-experience filter for that company.",
    "A job in an excluded industry is always SKIP, regardless of score.",
    "Credit only skills or experience present in the base resume or selected Final stories.",
)


def universal_resume_rules() -> tuple[str, ...]:
    return RESUME_RULES + ATS_RULES


def universal_cover_letter_rules() -> tuple[str, ...]:
    return COVER_LETTER_RULES


def universal_outreach_rules() -> tuple[str, ...]:
    return OUTREACH_RULES


def universal_evidence_rules() -> tuple[str, ...]:
    return EVIDENCE_RULES


def universal_ats_rules() -> tuple[str, ...]:
    return ATS_RULES


def universal_score_decision_rules() -> tuple[str, ...]:
    return SCORE_DECISION_RULES


def as_prompt_block(title: str, rules: tuple[str, ...]) -> str:
    """Render rules as a titled bullet block for an LLM system prompt."""
    lines = "\n".join(f"- {rule}" for rule in rules)
    return f"{title}:\n{lines}"
