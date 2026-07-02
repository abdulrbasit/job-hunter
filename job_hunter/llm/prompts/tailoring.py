"""Static prompt text for the tailoring role."""

from job_hunter.writing.rules import as_prompt_block, universal_resume_rules

SYSTEM_BASE = (
    "You are editing a LaTeX resume.\n"
    "Return ONLY the complete modified LaTeX file. No markdown fences, no explanation, no commentary.\n\n"
    + as_prompt_block("HARD RULES — NO EXCEPTIONS", universal_resume_rules())
)

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
