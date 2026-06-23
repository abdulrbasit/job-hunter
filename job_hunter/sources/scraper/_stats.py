"""Per-source yield diagnostics dataclasses for the scraper."""

from __future__ import annotations

import dataclasses
import logging
import threading

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class SourceStats:
    """Counts for a single named source during one scrape run."""

    attempted: int = 0
    returned: int = 0
    accepted: int = 0
    skipped: int = 0
    failed: int = 0
    exhausted: int = 0
    cached: int = 0


class ScrapeStats:
    """Accumulates per-source statistics during a scrape run.

    Thread-safe: individual source stat objects are created before the
    parallel phase and are only written by their owning thread (company
    processing is per-company) or under the main thread for global sources.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sources: dict[str, SourceStats] = {}

    def source(self, name: str) -> SourceStats:
        with self._lock:
            if name not in self._sources:
                self._sources[name] = SourceStats()
            return self._sources[name]

    def record(
        self,
        name: str,
        *,
        attempted: int = 0,
        returned: int = 0,
        accepted: int = 0,
        skipped: int = 0,
        failed: int = 0,
        exhausted: int = 0,
        cached: int = 0,
    ) -> None:
        s = self.source(name)
        with self._lock:
            s.attempted += attempted
            s.returned += returned
            s.accepted += accepted
            s.skipped += skipped
            s.failed += failed
            s.exhausted += exhausted
            s.cached += cached

    def log_summary(self, *, ats_only: bool = False) -> None:
        """Log a compact per-source summary at INFO level."""
        with self._lock:
            sources = dict(self._sources)
        if not sources:
            logger.info("[scraper][diag] no sources recorded")
            return
        header = "[scraper][diag] source yield summary:"
        if ats_only:
            header += " mode=ats-only"
        lines = [header]
        for name, s in sorted(sources.items()):
            parts = [f"attempted={s.attempted}", f"returned={s.returned}", f"accepted={s.accepted}"]
            if s.skipped:
                parts.append(f"skipped={s.skipped}")
            if s.failed:
                parts.append(f"failed={s.failed}")
            if s.exhausted:
                parts.append(f"exhausted={s.exhausted}")
            if s.cached:
                parts.append(f"cached={s.cached}")
            lines.append(f"  {name}: {', '.join(parts)}")
        logger.info("\n".join(lines))

    def to_dict(self) -> dict[str, dict]:
        with self._lock:
            return {name: dataclasses.asdict(s) for name, s in self._sources.items()}
