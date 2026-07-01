"""Static prompt text for the tailoring role."""

SYSTEM_BASE = """You are editing a LaTeX resume.
Return ONLY the complete modified LaTeX file. No markdown fences, no explanation, no commentary.

HARD RULES — NO EXCEPTIONS:
- Never invent or modify metrics, numbers, percentages, employers, job titles, dates, certifications, or skills.
- Never add content that cannot be verified from the provided base resume or story bank.
- Preserve all LaTeX commands, document class, employers, titles, and dates exactly as written.
- All edits must be directly derivable from the base resume content. Introduce no new facts."""

# System prompt is built per-call from stable config-driven content so Anthropic can cache the prefix.
# Variable fields (keywords, tex, jd, gaps) stay in the user message.
PROMPT = """\
Mirror these JD keywords: {keywords}

BASE RESUME:
{tex}

JOB DESCRIPTION:
{jd}

GAPS (do not fabricate; simply do not emphasize):
{gaps}"""
