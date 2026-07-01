"""Pure URL parsers for ATS job-description fetchers."""

from __future__ import annotations

import re
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


def personio_job_ref(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    host_match = re.match(r"^([^.]+)\.jobs\.personio\.(?:de|com)$", parsed.netloc.lower())
    if not host_match:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2 or parts[0] != "job":
        return None
    return host_match.group(1), parts[1]


def breezy_job_ref(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    host_match = re.match(r"^([^.]+)\.breezy\.hr$", parsed.netloc.lower())
    if not host_match:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2 or parts[0] != "p":
        return None
    return host_match.group(1), parts[1]


def recruitee_job_ref(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    host_match = re.match(r"^([^.]+)\.recruitee\.com$", parsed.netloc.lower())
    if not host_match:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2 or parts[0] != "o":
        return None
    return host_match.group(1), parts[1]


def teamtailor_job_ref(url: str) -> str | None:
    """Teamtailor's public feed has no single-job endpoint — the fetcher matches by
    full URL against the feed, so only the company slug is needed here."""
    parsed = urlparse(url)
    host_match = re.match(r"^([^.]+)\.teamtailor\.com$", parsed.netloc.lower())
    return host_match.group(1) if host_match else None


def workday_job_ref(url: str) -> tuple[str, str, str, str] | None:
    """Returns (tenant, wd_host_segment, site, external_path)."""
    parsed = urlparse(url)
    host_match = re.match(r"^([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com$", parsed.netloc.lower())
    if not host_match:
        return None
    tenant, wd_host = host_match.group(1), host_match.group(2)
    parts = [p for p in parsed.path.split("/") if p]
    if "job" not in parts:
        return None
    job_idx = parts.index("job")
    if job_idx == 0:
        return None
    site = parts[job_idx - 1]
    external_path = "/" + "/".join(parts[job_idx:])
    return tenant, wd_host, site, external_path
