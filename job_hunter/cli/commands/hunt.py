"""`job-hunter hunt` command."""

from __future__ import annotations

import typer

from job_hunter.cli.app import app


@app.command()
def hunt(
    region: str | None = typer.Option(None, "--region", "-r", help="Region key from config/job_hunter.yml"),
    depth: str = typer.Option("standard", "--depth", help="Scan depth: fast|standard|deep"),
    scrape_only: bool = typer.Option(False, "--scrape-only", help="Scrape and snapshot only; skip scoring"),
    from_snapshot: str | None = typer.Option(None, "--from-snapshot", help="Path to snapshot file"),
    skip_score: bool = typer.Option(False, "--skip-score"),
    skip_validate: bool = typer.Option(False, "--skip-validate"),
    force: bool = typer.Option(False, "--force", help="Reprocess already-seen jobs"),
) -> None:
    """Run job discovery and enrichment pipeline."""
    from job_hunter.cli._dispatch import dispatch_hunt

    dispatch_hunt(
        region_key=region,
        depth=depth,
        scrape_only=scrape_only,
        from_snapshot=from_snapshot,
        skip_score=skip_score,
        skip_validate=skip_validate,
        force=force,
    )
