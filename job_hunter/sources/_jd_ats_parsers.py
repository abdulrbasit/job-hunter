"""Pure URL parsers for ATS job-description fetchers."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse


def greenhouse_job_ref(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if "greenhouse.io" not in parsed.netloc.lower():
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 3 and parts[1] == "jobs" and parts[2].isdigit():
        return parts[0], parts[2]
    query = parse_qs(parsed.query)
    gh_jid = (query.get("gh_jid") or query.get("token") or [""])[0]
    if len(parts) >= 2 and parts[1] == "jobs" and gh_jid.isdigit():
        return parts[0], gh_jid
    return None


def ashby_job_ref(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() != "jobs.ashbyhq.com":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def lever_job_ref(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() != "jobs.lever.co":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def smartrecruiters_job_ref(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() != "jobs.smartrecruiters.com":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def workable_job_ref(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if parsed.netloc.lower() != "apply.workable.com":
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 3 and parts[1].lower() == "j":
        return parts[0], parts[2]
    return None
