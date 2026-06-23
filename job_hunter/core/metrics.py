"""Simple timing context manager for pipeline stages."""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any


@contextmanager
def timed_stage(logger: logging.Logger, name: str, **kwargs: Any) -> Generator[None, None, None]:
    """Log start/end and elapsed time for a named pipeline stage."""
    extra = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info("[stage:%s] starting — %s", name, extra)
    t0 = time.monotonic()
    try:
        yield
    finally:
        elapsed = time.monotonic() - t0
        logger.info("[stage:%s] done in %.1fs", name, elapsed)
