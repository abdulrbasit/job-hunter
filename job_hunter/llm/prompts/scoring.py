"""Static prompt text for the scoring role."""

from job_hunter.config.reference_data import student_mode
from job_hunter.core.posting_types import evidence_scoring_guidance

SYSTEM_BASE = (
    "You are a recruiter scoring job fit. "
    "Return ONLY valid JSON with no markdown fences, no explanation. "
    'Schema: {"score": int, "matched_keywords": [str], "gaps": [str], '
    '"years_exp_required": int or null, "role_summary": str, "score_rationale": str} '
    "Base your score only on evidence present in the provided resume. "
    "Do not infer unstated skills, experience, or qualifications."
)

REPAIR_PROMPT = """\
Convert this model response into valid JSON matching exactly this schema:
{{"score": int, "matched_keywords": [str], "gaps": [str], "years_exp_required": int|null, "role_summary": str, "score_rationale": str}}

Rules:
- Return ONLY valid JSON.
- If a field is missing or unclear, use score=0, matched_keywords=[], gaps=["parse repair"], years_exp_required=null, role_summary="", score_rationale="parse repair".

Response:
{raw}
"""

OPEN_CHECK_SYSTEM = (
    "You are screening job postings. "
    'Return ONLY valid JSON: {"open": bool, "reason": str}. '
    "Set open=true if the posting appears to be actively accepting applications. "
    "Set open=false if it shows signs of being closed, filled, or expired. "
    "Set open=null if genuinely uncertain."
)


def scoring_guidance(config: dict) -> str:
    """Return concise evidence-weighting guidance for the selected career track."""
    return evidence_scoring_guidance(is_student=student_mode(config))
