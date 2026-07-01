"""LinkedIn workflow CLI commands."""

from __future__ import annotations

import typer

from job_hunter.cli.app import linkedin_app


@linkedin_app.command("ideas")
def linkedin_ideas() -> None:
    """Generate raw LinkedIn content ideas."""
    from job_hunter.linkedin.ideas import generate

    created = generate()
    typer.echo(f"[linkedin] ideas: {len(created)}")


@linkedin_app.command("draft")
def linkedin_draft() -> None:
    """Draft LinkedIn posts from unconverted ideas."""
    from job_hunter.linkedin.drafts import draft

    created = draft()
    typer.echo(f"[linkedin] drafts: {len(created)}")


@linkedin_app.command("network")
def linkedin_network() -> None:
    """Discover LinkedIn networking suggestions and draft review text."""
    from job_hunter.linkedin.engagement import discover

    payload = discover()
    typer.echo(f"[linkedin] recruiters: {len(payload['recruiters'])}; people: {len(payload['people'])}")


@linkedin_app.command("all")
def linkedin_all() -> None:
    """Run LinkedIn ideas, drafts, and networking."""
    from job_hunter.linkedin.drafts import draft
    from job_hunter.linkedin.engagement import discover
    from job_hunter.linkedin.ideas import generate

    ideas = generate()
    drafts = draft()
    network = discover()
    typer.echo(
        f"[linkedin] ideas: {len(ideas)}; drafts: {len(drafts)}; "
        f"recruiters: {len(network['recruiters'])}; people: {len(network['people'])}"
    )
