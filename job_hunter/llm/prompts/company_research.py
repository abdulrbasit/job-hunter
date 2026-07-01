"""Static prompt text for the research (company research) role."""

SYSTEM = (
    "You write concise company research notes for job applications. "
    "Use only factual information from your training data. "
    "If uncertain about a claim, omit it. No speculation."
)

PROMPT = """\
Write company research for a {title} applicant targeting {company}.

Use this exact structure (plain text, under 300 words total):

## Product & Business
<2-3 sentences on what the company builds and for whom>

## Tech Stack / Engineering
<known technologies and engineering practices>

## Culture Signals
<reputation, glassdoor signals, engineering blog if known>

## Recent News
<notable events from training data>

## Application Angle
<one line on how this context informs the cover letter or story selection>"""
