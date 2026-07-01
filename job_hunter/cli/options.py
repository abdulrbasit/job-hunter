"""Shared Typer option definitions — avoids re-declaring identical options per command."""

from __future__ import annotations

import typer

WORKSPACE_OPTION = typer.Option(".", "--workspace", "-w")
JSON_OPTION = typer.Option(False, "--json")
