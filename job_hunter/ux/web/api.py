"""Python JS API exposed to the pywebview dashboard via window.pywebview.api.*"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DashAPI:
    def __init__(self, root: Path) -> None:
        self._root = root

    def get_applications(self) -> list[dict[str, Any]]:
        from job_hunter.tracking.applications import filtered_applications

        return [dict(app) for app in filtered_applications(root=self._root)]

    def get_job_detail(self, slug: str) -> dict[str, Any]:
        from job_hunter.tracking.repository import get_job_by_slug

        record = get_job_by_slug(self._root, slug) or {}
        if record:
            return {
                "slug": slug,
                "meta": {
                    "title": record.get("title"),
                    "company": record.get("company"),
                    "location": record.get("location"),
                    "url": record.get("url"),
                    "region": record.get("region"),
                    "job_description_fetch_status": record.get("job_description_fetch_status"),
                },
                "score": {
                    "score": record.get("score"),
                    "decision": record.get("decision"),
                    "matched": record.get("matched_keywords") or [],
                    "gaps": record.get("gaps") or [],
                    "score_rationale": record.get("score_rationale"),
                    "recommendation": record.get("recommendation"),
                },
                "jd": (record.get("jd_text") or "")[:4000],
            }

        # Fallback: read job folder files (legacy)
        job_dir = self._root / "outputs" / "jobs" / slug
        meta: dict[str, Any] = {}
        score: dict[str, Any] = {}
        jd_text = ""

        meta_path = job_dir / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))

        score_path = job_dir / "score.yml"
        if score_path.exists():
            import yaml

            score = yaml.safe_load(score_path.read_text(encoding="utf-8")) or {}

        jd_path = job_dir / "jd.md"
        if jd_path.exists():
            jd_text = jd_path.read_text(encoding="utf-8")[:4000]

        return {"slug": slug, "meta": meta, "score": score, "jd": jd_text}

    def _refresh_readme(self) -> None:
        from datetime import date

        from job_hunter.pipeline.stages.readme import update_readme_from_applications
        from job_hunter.tracking.applications import load_applications

        apps = load_applications(self._root)["applications"]
        update_readme_from_applications(apps, self._root, date.today().isoformat())

    def update_status(self, slug: str, status: str, note: str = "") -> dict[str, Any]:
        from job_hunter.tracking.applications import update_application_status

        try:
            result = dict(update_application_status(slug, status, root=self._root, note=note))
        except (ValueError, KeyError) as exc:
            return {"error": str(exc)}
        self._refresh_readme()
        return result

    def delete_application(self, slug: str) -> bool:
        from job_hunter.tracking.applications import delete_application

        try:
            delete_application(slug, self._root)
        except Exception:  # noqa: BLE001
            return False
        self._refresh_readme()
        return True

    def get_insights(self) -> dict[str, Any]:
        from collections import defaultdict

        from job_hunter.tracking.applications import filtered_applications
        from job_hunter.ux.analytics import analyze_pipeline

        report = analyze_pipeline(self._root)
        weekly: dict[str, int] = defaultdict(int)
        for app in filtered_applications(root=self._root):
            date_str = str(app.get("discovered_at") or app.get("created_at") or "")[:10]
            if date_str:
                from datetime import date as _date

                try:
                    d = _date.fromisoformat(date_str)
                    week_key = f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
                    weekly[week_key] += 1
                except ValueError:
                    pass

        report["weekly"] = dict(sorted(weekly.items())[-12:])
        return report

    def get_analytics(self) -> dict[str, Any]:
        from job_hunter.metrics.store import get_runs

        db_path = self._root / "outputs" / "state" / "metrics.db"
        runs = get_runs(db_path)
        return {"runs": runs}

    def get_user_name(self) -> str:
        """Extract candidate name from LaTeX resume via \\name{...}."""
        import re

        from job_hunter.config.loader import get_config

        config = get_config("job_hunter")
        tex_rel = config.get("profile", {}).get("resume_tex", "profile/resume_double_column.tex")
        tex_path = self._root / tex_rel
        if tex_path.exists():
            m = re.search(r"\\name\{([^}]+)\}", tex_path.read_text(encoding="utf-8"))
            if m:
                return m.group(1).strip()
        return ""
