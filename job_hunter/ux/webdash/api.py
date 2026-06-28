"""Python JS API exposed to the pywebview dashboard via window.pywebview.api.*"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


class DashAPI:
    def __init__(self, root: Path) -> None:
        self._root = root

    def get_applications(self) -> list[dict[str, Any]]:
        from job_hunter.ux.applications import filtered_applications

        return [dict(app) for app in filtered_applications(root=self._root)]

    def get_job_detail(self, slug: str) -> dict[str, Any]:
        job_dir = self._root / "outputs" / "jobs" / slug
        meta: dict[str, Any] = {}
        score: dict[str, Any] = {}
        jd_text = ""

        meta_path = job_dir / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))

        score_path = job_dir / "score.yml"
        if score_path.exists():
            score = yaml.safe_load(score_path.read_text(encoding="utf-8")) or {}

        jd_path = job_dir / "jd.md"
        if jd_path.exists():
            jd_text = jd_path.read_text(encoding="utf-8")[:4000]

        return {
            "slug": slug,
            "meta": meta,
            "score": score,
            "jd": jd_text,
        }

    def update_status(self, slug: str, status: str, note: str = "") -> dict[str, Any]:
        from job_hunter.ux.applications import update_application_status

        try:
            return dict(update_application_status(slug, status, root=self._root, note=note))
        except (ValueError, KeyError) as exc:
            return {"error": str(exc)}

    def delete_application(self, slug: str) -> bool:
        from job_hunter.ux.applications import delete_application

        try:
            delete_application(slug, self._root)
            return True
        except Exception:  # noqa: BLE001
            return False

    def get_insights(self) -> dict[str, Any]:
        from collections import defaultdict

        from job_hunter.ux.analytics import analyze_pipeline
        from job_hunter.ux.applications import filtered_applications

        report = analyze_pipeline(self._root)
        # weekly activity: group apps by ISO week

        weekly: dict[str, int] = defaultdict(int)
        for app in filtered_applications(root=self._root):
            date_str = str(app.get("date") or "")[:10]
            if date_str:
                from datetime import date as _date

                try:
                    d = _date.fromisoformat(date_str)
                    week_key = f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"
                    weekly[week_key] += 1
                except ValueError:
                    pass

        report["weekly"] = dict(sorted(weekly.items())[-12:])  # last 12 weeks
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

        cfg = get_config("job_hunter")
        tex_rel = cfg.get("profile", {}).get("resume_tex", "profile/resume_double_column.tex")
        tex_path = self._root / tex_rel
        if tex_path.exists():
            m = re.search(r"\\name\{([^}]+)\}", tex_path.read_text(encoding="utf-8"))
            if m:
                return m.group(1).strip()
        return ""
