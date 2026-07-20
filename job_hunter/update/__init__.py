"""In-app update machinery: PyPI version check, upgrader detection, snapshot/rollback of
system-owned workspace files, changelog lookup, and the detached self-update helper.

Package-owned, read-only to the user — no new user-config surface. State this package
writes (update-check cache, last-update result) lives in launcher.platform_config_dir(),
not the workspace; snapshots live under outputs/state/ (already user-owned/regenerable
per DATA_CONTRACT.md). May depend on config/ and workspace/; must not depend on ux/,
cli/, or pipeline/ (ux/ depends on update/, not the reverse).
"""

from __future__ import annotations
