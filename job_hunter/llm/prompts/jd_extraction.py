"""Static prompt text for the jd_extraction role."""

SYSTEM = "You are a job posting parser. Return ONLY valid JSON with no markdown fences and no explanation."

PROMPT = """\
Extract the job details from this job posting page text.

URL: {url}

PAGE TEXT (first 8000 chars):
{text}

Return JSON:
{{
  "title": "exact job title from the posting",
  "company": "company name",
  "description": "the full job description text including responsibilities and requirements — at least 400 words if available"
}}

If a field cannot be found, use null."""
