"""Workspace root path helper."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path


def repo_path(*parts: str) -> Path:
    """Return ROOT / parts, or ROOT if no parts given."""
    from job_hunter.config.loader import ROOT

    if not parts:
        return ROOT
    return ROOT.joinpath(*parts)


def read_optional(path: Path) -> str:
    """Read a text file, returning empty string if it doesn't exist."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def today_path(subdir: str) -> Path:
    """Return ROOT/subdir/YYYY-MM-DD_<subdir>.md, creating parent dirs as needed."""
    today = date.today().isoformat()
    from job_hunter.config.loader import ROOT

    dest = ROOT / subdir / f"{today}_{subdir.replace('/', '_')}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def write_artifact(path: Path, content: str) -> Path:
    """Write content to path, creating parent dirs. Returns path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "job"


def _looks_like_generic_listing(url: str, text: str) -> bool:
    if "greenhouse.io" in url.lower() and not re.search(r"/jobs/\d+", url, re.IGNORECASE):
        return True
    normalized = re.sub(r"\s+", " ", text.lower())
    listing_markers = (
        "open positions",
        "current openings",
        "job openings",
        "view all jobs",
        "departments",
        "all departments",
    )
    role_markers = (
        "responsibilities",
        "requirements",
        "qualifications",
        "about the role",
        "what you'll do",
        "what you will do",
    )
    return sum(1 for marker in listing_markers if marker in normalized) >= 2 and not any(
        marker in normalized for marker in role_markers
    )


def latest_candidate_snapshot() -> Path | None:
    candidate_dir = repo_path("outputs", "candidates")
    if not candidate_dir.exists():
        return None
    files = []
    for pattern in ("*_candidates.yml", "*_candidates.json", "*_job_candidates.yml"):
        files.extend(candidate_dir.glob(pattern))
    files = sorted(files, key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def import_job_artifact(
    *,
    title: str = "",
    company: str = "",
    url: str = "",
    text: str = "",
    fallback_text: str = "",
    source_path: Path | None = None,
    region: str = "",
    location: str = "",
) -> Path:
    from job_hunter.pipeline.enrichment import JD_STATUS_FULL, classify_jd_snippet

    fetch_status = "manual_text" if text else "not_requested"
    if source_path:
        text = read_optional(source_path)
        fetch_status = "source_file"
    if url and not text and not url.lower().startswith(("http://", "https://")):
        if fallback_text:
            text = fallback_text
            fetch_status = "fallback_snippet"
    elif url and not text:
        try:
            from job_hunter.sources.jd_fetcher import fetch_jd

            fetched = fetch_jd(url, expected_title=title)
            if fetched:
                text = fetched.get("snippet", "")
                title = title or fetched.get("title", "")
                company = company or fetched.get("company", "")
                url = fetched.get("url", url)
                fetch_status = fetched.get("source", "fetched")
            elif (
                fallback_text
                and classify_jd_snippet(fallback_text) == JD_STATUS_FULL
                and not _looks_like_generic_listing(url, fallback_text)
            ):
                text = fallback_text
                fetch_status = "fallback_snippet"
            else:
                fetch_status = "fetch_failed"
        except Exception:
            if (
                fallback_text
                and classify_jd_snippet(fallback_text) == JD_STATUS_FULL
                and not _looks_like_generic_listing(url, fallback_text)
            ):
                text = fallback_text
                fetch_status = "fallback_snippet"
            else:
                fetch_status = "fetch_failed"
    role = title or "Imported Role"
    org = company or "Unknown Company"
    slug = f"{date.today().isoformat()}_{slugify(org)}_{slugify(role)}"
    folder = repo_path("outputs", "jobs", slug)
    folder.mkdir(parents=True, exist_ok=True)
    meta = {
        "date": date.today().isoformat(),
        "title": role,
        "company": org,
        "url": url,
        "source": "manual-import",
        "status": "imported",
        "region": region or "",
        "location": location or "",
        "fetch_status": fetch_status,
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (folder / "jd.md").write_text(
        f"# {role} @ {org}\n\n"
        f"URL: {url or 'Not provided'}\n\n"
        f"{text.strip() or 'Paste the job description here before scoring or tailoring.'}\n",
        encoding="utf-8",
    )
    (folder / "score.yml").write_text(
        "# score_job output - filled by agent\nstatus: pending\n",
        encoding="utf-8",
    )
    (folder / "cover_letter.md").write_text(
        "# Cover Letter\n\n<!-- agent writes cover letter here -->\n",
        encoding="utf-8",
    )
    (folder / "evaluation.md").write_text(
        f"# Evaluation - {role} @ {org}\n\n"
        "## Role Summary\n\n"
        "Pending scoring.\n\n"
        "## Score Rationale\n\n"
        "Pending scoring.\n\n"
        "## Verified Evidence\n\n"
        "Pending scoring.\n\n"
        "## Gaps And Risks\n\n"
        "Pending scoring.\n\n"
        "## Company Notes\n\n"
        "Pending research.\n\n"
        "## Interview Prep Hooks\n\n"
        "Pending scoring.\n\n"
        "## Recommendation\n\n"
        "Pending scoring.\n",
        encoding="utf-8",
    )
    return folder
