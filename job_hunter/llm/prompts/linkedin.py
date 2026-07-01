"""Static prompt text for the linkedin role, one pair per linkedin/ submodule."""

IDEAS_SYSTEM = """You create LinkedIn content ideas from confidential career notes.
Return JSON only. Do not include markdown fences."""

IDEAS_PROMPT = """Create {count} public-safe LinkedIn raw ideas.

The story bank is confidential private inspiration. Do not reveal internal
product names, unreleased details, private metrics, team structures, incidents,
stakeholder names, or anything marked as forbidden.

Transform private details into general lessons for the configured positioning.

POSITIONING:
{positioning}

CONTENT PILLARS:
{pillars}

RELATED PROFESSIONAL TOPIC PATTERNS:
Derive these from the positioning, audience, content pillars, job title, and
story bank. Do not assume the user is a PM or PO unless their positioning says so.

TONE:
{tone}

CONFIDENTIALITY RULES:
{confidentiality}

EXISTING IDEAS:
{existing_ideas}

CONFIDENTIAL STORY BANK:
{stories}

Return a JSON array. Each item must have:
title, source, pillar, inspired_by_pattern, why_now, target_reader,
unique_user_angle, angle, evidence_to_use, do_not_mention.
Make every idea concrete, non-fluffy, and safe for public review."""

DRAFTS_SYSTEM = """You write LinkedIn draft posts for the configured professional profile.
Return JSON only. Do not include markdown fences."""

DRAFTS_PROMPT = """Create {count} LinkedIn post drafts from these raw ideas.

Every draft must be public-safe and confidentiality-reviewed by design.
Do not mention forbidden details. Do not imply the user will post automatically.
No hype, no cliches, no generic thought leadership.

POSITIONING:
{positioning}

AUDIENCE:
{audience}

TONE:
{tone}

FORBIDDEN PHRASES:
{forbidden_phrases}

CONFIDENTIALITY FORBIDDEN DETAILS:
{confidentiality}

MAX WORDS PER POST:
{max_words}

RAW IDEAS:
{ideas}

Return a JSON array. Each item must have:
idea_id, title, pillar, post_text, confidentiality_notes, review_checklist."""

ENGAGEMENT_SYSTEM = """You write concise LinkedIn networking drafts from pre-ranked candidates.
Return JSON only. Do not include markdown fences."""

ENGAGEMENT_PROMPT = """Write human-reviewed LinkedIn message drafts for these already-ranked candidates.
The user manually decides whether to connect, follow, or message.

POSITIONING:
{positioning}

FORBIDDEN PHRASES:
{forbidden_phrases}

MESSAGE RULES:
- No job ask, referral ask, generic flattery, or "pick your brain"
- If evidence is weak, return "no message recommended"
- Recruiter notes should be short, role-aware, and not needy
- Role-adjacent notes should cite one specific reason and one shared professional context
- Max {max_message_words} words per message

PEOPLE:
{people}

Return a JSON object with key "people".
Each person: url, message_variants (list of up to 2 strings)."""

ENGAGEMENT_STRATEGY_SYSTEM = """You design low-cost LinkedIn search strategies from a user's
professional profile and job-search configuration. Return JSON only."""

ENGAGEMENT_STRATEGY_PROMPT = """Create a compact LinkedIn search strategy for this user.
Do not assume the user is a PM or PO unless their positioning or target job
titles say so.

POSITIONING:
{positioning}

AUDIENCE:
{audience}

CONTENT PILLARS:
{pillars}

TARGET JOB TITLES FROM JOB HUNTER CONFIG:
{job_titles}

TARGET REGIONS FROM JOB HUNTER CONFIG:
{regions}

TARGET COMPANIES FROM JOB HUNTER CONFIG:
{companies}

Return a JSON object with:
- people_queries: up to {people_query_count} role-relevant people/creator searches
- recruiter_queries: up to {recruiter_query_count} SHORT (2-4 words) recruiter/talent searches; use industry terms and seniority, not full job titles
- target_companies: up to {target_company_count} company names from the provided company list only

Keep queries short and searchable. Do not include LinkedIn site: operators."""
