"""Static prompt text for the validation role."""

SYSTEM = "You are a job-posting validator. Return ONLY valid JSON with no markdown fences and no explanation."

PROMPT = """\
Read this job posting snippet and answer three questions.

1. Is this an active, open posting?
   Mark is_active=false ONLY if the text explicitly says the role is filled,
   closed, expired, archived, or no longer accepting applications.
   When in doubt, default to true.

2. Does this posting explicitly require MORE than {max_years} years of experience?
   Mark over_experience=true ONLY if the description clearly states a minimum
   exceeding {max_years} years (e.g. "10+ years required", "minimum 8 years").
   When in doubt, default to false.

3. Is the EMPLOYER itself primarily in one of these excluded industries: {excluded_industries}?
   Do not reject because the role serves those customers, builds a related feature, or mentions
   compliance. Mark excluded_industry=true only when the employer's primary business clearly matches.
   When in doubt, default to false.

Snippet:
{snippet}

Return JSON: {{"is_active": bool, "over_experience": bool, "excluded_industry": bool,
"reason": "one-line reason if rejected, else null"}}"""

REPAIR_PROMPT = """\
Convert this model response into valid JSON matching exactly this schema:
{{"is_active": bool, "over_experience": bool, "excluded_industry": bool, "reason": string|null}}

Rules:
- Return ONLY valid JSON.
- If a value is missing or unclear, use is_active=true, over_experience=false,
  excluded_industry=false, reason=null.

Response:
{raw}
"""
