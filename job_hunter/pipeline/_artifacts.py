"""Job-run artifact writers for pipeline processing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


def write_match_artifacts(match: dict[str, Any], job_dir: Path, *, today: str) -> None:
    job = match["job"]
    meta = {
        "date": today,
        "title": job["title"],
        "company": job["company"],
        "url": job["url"],
        "location": job.get("location", ""),
        "posted": job.get("posted", ""),
        "score": match["score"],
        "matched_keywords": match.get("matched", match.get("matched_keywords", [])),
        "gaps": match.get("gaps", []),
        "source": job.get("source", "scraped"),
    }
    (job_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    score_data = {
        "score": match["score"],
        "decision": match.get("decision", "APPLY"),
        "matched_story_ids": match.get("matched_story_ids", []),
        "matched": match.get("matched", match.get("matched_keywords", [])),
        "gaps": match.get("gaps", []),
        "role_summary": match.get("role_summary", ""),
        "score_rationale": match.get("score_rationale", ""),
        "recommendation": match.get("recommendation", ""),
    }
    (job_dir / "score.yml").write_text(yaml.safe_dump(score_data, allow_unicode=True), encoding="utf-8")
    (job_dir / "jd.md").write_text(
        f"# {job['title']} @ {job['company']}\n\n"
        f"**URL:** {job['url']}\n\n"
        f"**Location:** {job.get('location', 'Unknown')}\n\n"
        f"**Posted:** {job.get('posted', 'Unknown')}\n\n"
        f"{job['snippet']}",
        encoding="utf-8",
    )
