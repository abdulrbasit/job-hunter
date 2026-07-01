"""README job table rendering for processed matches."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

TABLE_START = "<!-- JOBS_TABLE_START -->"
TABLE_END = "<!-- JOBS_TABLE_END -->"
STATS_START = "<!-- JOBS_STATS_START -->"
STATS_END = "<!-- JOBS_STATS_END -->"
TABLE_HEADER = "| Date | Job | Location | Score | Files |\n|---|---|---|---|---|"


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"\s+", "-", text.strip())[:50]


def _parse_existing_rows(table_body: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in table_body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        url_match = re.search(r"\]\((https?://[^)]+)\)", line)
        if url_match:
            rows[url_match.group(1)] = _ensure_location_column(line)
    return rows


def _ensure_location_column(row: str) -> str:
    try:
        left, files_tail = row.rsplit(" | [Files](", 1)
        before_score, score = left.rsplit(" | ", 1)
    except ValueError:
        return row

    before_score = _escape_link_text_pipes(before_score)
    link_end = before_score.rfind(")")
    has_location = link_end != -1 and before_score[link_end + 1 :].strip().startswith("|")
    if not has_location:
        return f"{before_score} | Unknown | {score} | [Files]({files_tail}"
    return f"{before_score} | {score} | [Files]({files_tail}"


def _escape_table_cell(value: object) -> str:
    return str(value or "Unknown").replace("\n", " ").replace("|", r"\|")


def _escape_link_text_pipes(value: str) -> str:
    def _replace(match: re.Match) -> str:
        text = re.sub(r"(?<!\\)\|", r"\\|", match.group(1))
        return f"[{text}]({match.group(2)})"

    return re.sub(
        r"\[([^\]]*)\]\((https?://[^)]+)\)",
        _replace,
        value,
    )


def _job_location(job: dict) -> str:
    return _escape_table_cell(job.get("location") or job.get("region") or "Unknown")


def _row_date(row: str) -> datetime | None:
    match = re.match(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|", row)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d")
    except ValueError:
        return None


def _stats_block(rows: list[str], today: str) -> str:
    if not rows:
        return f"{STATS_START}\nNo jobs tracked yet.\n{STATS_END}\n\n"

    dates = [date for row in rows if (date := _row_date(row))]
    if not dates:
        return f"{STATS_START}\n**Application stats:** {len(rows)} jobs tracked.\n{STATS_END}\n\n"

    start_date = min(dates)
    try:
        as_of = datetime.strptime(today, "%Y-%m-%d")
    except ValueError:
        as_of = max(dates)
    weeks = max(1, ((as_of - start_date).days + 6) // 7)
    label = "job" if len(rows) == 1 else "jobs"
    week_label = "week" if weeks == 1 else "weeks"
    return (
        f"{STATS_START}\n"
        f"**Application stats:** {len(rows)} {label} tracked since "
        f"{start_date:%Y-%m-%d} ({weeks} {week_label}).\n"
        f"{STATS_END}\n\n"
    )


def _replace_stats_block(content: str, stats: str, table_start_idx: int) -> str:
    stats_start_idx = content.find(STATS_START)
    stats_end_idx = content.find(STATS_END)
    if stats_start_idx != -1 and stats_end_idx != -1 and stats_start_idx < table_start_idx:
        return re.sub(
            rf"\n*{re.escape(STATS_START)}.*?{re.escape(STATS_END)}\n*",
            f"\n\n{stats}",
            content,
            count=1,
            flags=re.DOTALL,
        )
    return content[:table_start_idx].rstrip() + f"\n\n{stats}" + content[table_start_idx:].lstrip("\n")


def update_readme(matches: list[dict], root: str | Path, today: str) -> None:
    logger.info("[readme] Updating with %s job(s)", len(matches))
    readme_path = Path(root) / "README.md"
    try:
        content = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
        start_idx = content.find(TABLE_START)
        end_idx = content.find(TABLE_END)
        if start_idx == -1 or end_idx == -1:
            logger.warning("[readme] Markers not found - skipping update")
            return
        table_block = content[start_idx + len(TABLE_START) : end_idx]
        existing_rows = _parse_existing_rows(table_block)
        for match in sorted(matches, key=lambda x: x["score"], reverse=True):
            job = match["job"]
            slug = f"{today}_{slugify(job['company'])}_{slugify(job['title'])}"
            label = _escape_table_cell(f"{job['title']} @ {job['company']}")
            existing_rows[job["url"]] = (
                f"| {today} | [{label}]({job['url']}) | {_job_location(job)}"
                f" | {match['score']} | [Files](jobs/{slug}/) |"
            )
        all_rows = sorted(existing_rows.values(), reverse=True)
        new_table = f"\n{TABLE_HEADER}\n" + "\n".join(all_rows) + "\n"
        content = _replace_stats_block(content, _stats_block(all_rows, today), start_idx)
        start_idx = content.find(TABLE_START)
        end_idx = content.find(TABLE_END)
        updated = content[:start_idx] + TABLE_START + new_table + TABLE_END + content[end_idx + len(TABLE_END) :]
        readme_path.write_text(updated, encoding="utf-8")
        logger.info("[readme] Table now has %s row(s)", len(all_rows))
    except Exception as e:
        logger.error("[readme] Update failed: %s", e)
        raise


def update_readme_from_applications(apps: list[dict], root: str | Path, today: str) -> None:
    """Rewrite README table from application dicts — authoritative, replaces existing rows."""
    logger.info("[readme] Updating from %s application(s)", len(apps))
    readme_path = Path(root) / "README.md"
    try:
        content = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
        start_idx = content.find(TABLE_START)
        end_idx = content.find(TABLE_END)
        if start_idx == -1 or end_idx == -1:
            logger.warning("[readme] Markers not found - skipping update")
            return
        all_rows = []
        for app in sorted(apps, key=lambda a: a.get("score", 0) or 0, reverse=True):
            job = {
                "title": app.get("title", ""),
                "company": app.get("company", ""),
                "url": app.get("url", ""),
                "location": app.get("location", ""),
            }
            slug = app.get("slug") or f"{app.get('date', today)}_{slugify(job['company'])}_{slugify(job['title'])}"
            status = app.get("status", "")
            status_suffix = f" ({status})" if status else ""
            score = app.get("score", 0)
            label = _escape_table_cell(f"{job['title']} @ {job['company']}")
            all_rows.append(
                f"| {today} | [{label}]({job['url']}) | {_job_location(job)}"
                f" | {score}{status_suffix} | [Files](outputs/jobs/{slug}/) |"
            )
        all_rows.sort(reverse=True)
        new_table = f"\n{TABLE_HEADER}\n" + "\n".join(all_rows) + "\n"
        content = _replace_stats_block(content, _stats_block(all_rows, today), start_idx)
        start_idx = content.find(TABLE_START)
        end_idx = content.find(TABLE_END)
        updated = content[:start_idx] + TABLE_START + new_table + TABLE_END + content[end_idx + len(TABLE_END) :]
        readme_path.write_text(updated, encoding="utf-8")
        logger.info("[readme] Table now has %s row(s)", len(all_rows))
    except Exception as e:
        logger.error("[readme] Update failed: %s", e)
        raise
