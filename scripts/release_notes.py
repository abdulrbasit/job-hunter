#!/usr/bin/env python3
"""Generate release notes body for a given version tag."""

import os
import subprocess

v = os.environ["VERSION"]
prev = os.environ.get("PREV", "")
range_arg = f"{prev}..v{v}^" if prev else f"v{v}^"
extra: list[str] = [] if prev else ["--max-count=50"]
notes = subprocess.check_output(  # noqa: S603, S607
    ["git", "log", range_arg, "--oneline", "--no-decorate", "--no-merges"] + extra,
    text=True,
).strip()
print(
    f"## Changes in v{v}\n\n"
    f"{notes or 'No changes.'}\n\n"
    f"**Install / upgrade:**\n"
    f'```\npip install --upgrade "job-hunter-kit=={v}"\n```'
)
