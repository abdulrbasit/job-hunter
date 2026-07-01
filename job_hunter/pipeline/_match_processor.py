"""Single-match processing helpers for the job pipeline."""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from job_hunter.llm.prompts.company_research import PROMPT as _RESEARCH_PROMPT
from job_hunter.llm.prompts.company_research import SYSTEM as _RESEARCH_SYSTEM


def copy_latex_assets(job_dir: Path, profile_path: Callable[[str, str], Path]) -> None:
    for src in (
        profile_path("latex_class", "altacv.cls"),
        profile_path("profile_image", ""),
    ):
        if src.exists():
            shutil.copy2(src, job_dir / src.name)


def write_company_research(
    job: dict[str, Any],
    job_dir: Path,
    *,
    get_config: Callable[[str], dict[str, Any]],
    llm_stage_factory: Callable[[str], Any],
    logger: Any,
) -> None:
    """Write company_research.md via LLM using training-data knowledge."""
    config = get_config("job_hunter")
    titles = ", ".join(config.get("job_titles") or []) or "the role"
    company = job.get("company", "Unknown")
    title = job.get("title") or titles

    stage = llm_stage_factory("research")
    prompt = _RESEARCH_PROMPT.format(title=title, company=company)
    try:
        content = stage.complete(system=_RESEARCH_SYSTEM, user=prompt)
        (job_dir / "company_research.md").write_text(f"# {company} Research\n\n{content}", encoding="utf-8")
        logger.info("  company research written")
    except Exception as exc:
        logger.warning("  company research failed: %s - continuing", exc)


def make_generated_tex_self_contained(tex: str, profile_path: Callable[[str, str], Path]) -> str:
    latex_class = profile_path("latex_class", "altacv.cls")
    profile_image = profile_path("profile_image", "")

    if latex_class.exists() or latex_class.name:
        class_stem = re.escape(latex_class.stem)
        tex = re.sub(
            rf"(\\documentclass(?:\[[^\]]*\])?)\{{(?:[./\\]+)?(?:.*[./\\])?{class_stem}\}}",
            rf"\1{{{latex_class.stem}}}",
            tex,
            count=1,
        )

    if profile_image.exists() or profile_image.name:
        image_stem = re.escape(profile_image.stem)
        tex = re.sub(
            rf"(\\photoR\{{[^}}]+\}})\{{(?:[./\\]+)?(?:.*[./\\])?{image_stem}\}}",
            rf"\1{{{profile_image.stem}}}",
            tex,
            count=1,
        )

    return tex


def process_match(
    match: dict[str, Any],
    *,
    today: Callable[[], str],
    jobs_dir: Path,
    slugify: Callable[[str], str],
    write_match_artifacts: Callable[..., None],
    write_company_research: Callable[[dict[str, Any], Path], None],
    tailor: Callable[[dict[str, Any]], str],
    make_tex_self_contained: Callable[[str], str],
    copy_latex_assets: Callable[[Path], None],
    compile_tex: Callable[[str, str], str | None],
    write_cover: Callable[[dict[str, Any], str], None],
    logger: Any,
) -> bool:
    """
    Tailor, compile PDF, and write cover letter for a single matched job.
    Returns True on full success, False if a critical step fails.
    PDF compilation is non-critical; failure there does not abort the job.
    """
    job = match["job"]
    slug = f"{today()}_{slugify(job['company'])}_{slugify(job['title'])}"
    job_dir = jobs_dir / slug
    job_dir.mkdir(exist_ok=True)

    write_match_artifacts(match, job_dir, today=today())

    logger.info("  Researching company...")
    write_company_research(job, job_dir)

    logger.info("  Tailoring resume...")
    try:
        tex_path = job_dir / "resume_tailored.tex"
        tex_path.write_text(make_tex_self_contained(tailor(match)), encoding="utf-8")
        copy_latex_assets(job_dir)
        logger.info("  resume tailored")
    except Exception as exc:
        logger.error("  tailoring failed: %s", exc)
        return False

    logger.info("  Compiling PDF...")
    try:
        pdf = compile_tex(str(tex_path), str(job_dir))
        logger.info("  PDF %s", "generated" if pdf else "(LaTeX saved, no PDF)")
    except Exception as exc:
        logger.warning("  PDF compilation failed: %s - continuing", exc)

    logger.info("  Writing cover letter...")
    try:
        write_cover(match, str(job_dir))
        logger.info("  cover letter written")
    except Exception as exc:
        logger.error("  cover letter failed: %s", exc)
        return False

    logger.info("  complete -> jobs/%s/", slug)
    return True
