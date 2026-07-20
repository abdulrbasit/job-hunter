"""Curated model IDs for the guided-form per-role dropdown.

Two tiers per hosted provider — a fast/cheap option and a stronger balanced
option — deliberately excludes each provider's most expensive flagship tier.
Ollama is self-hosted with unbounded model names, so it stays free-text in
the guided form rather than appearing here.

Model IDs go stale as providers release new versions; review periodically.
"""

from __future__ import annotations

MODEL_CATALOG: dict[str, list[str]] = {
    "anthropic": ["claude-haiku-4-5-20251001", "claude-sonnet-5"],
    "openai": ["gpt-5.6-luna", "gpt-5.6-terra"],
    "google": ["gemini-3.1-flash-lite", "gemini-2.5-pro"],
}
