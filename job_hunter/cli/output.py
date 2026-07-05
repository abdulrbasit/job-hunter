"""Shared CLI output/error helpers."""

from __future__ import annotations

from typing import NoReturn

import typer


def fail(message: str, *, code: int = 1) -> NoReturn:
    """Echo an error message to stderr and exit with the given code. Never returns."""
    typer.echo(message, err=True)
    raise typer.Exit(code)
