"""`job-hunter tailor` command."""

from __future__ import annotations

from pathlib import Path

import typer

from job_hunter.cli.app import app
from job_hunter.cli.output import fail


@app.command()
def tailor(
    links: str | None = typer.Option(None, "--links", help="Comma-separated job URLs"),
    jd_file: str | None = typer.Option(None, "--jd-file", help="Path to JD text file"),
    title: str | None = typer.Option(None, "--title"),
    company: str | None = typer.Option(None, "--company"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Tailor resume for one or more job postings."""
    from job_hunter.cli._dispatch import dispatch_tailor

    if links:
        dispatch_tailor(links=links, title=title, company=company, force=force)
        return
    if jd_file:
        jd_text = Path(jd_file).read_text(encoding="utf-8")
        dispatch_tailor(jd_text=jd_text, title=title, company=company, force=force)
        return
    fail("[tailor] provide --links or --jd-file")
