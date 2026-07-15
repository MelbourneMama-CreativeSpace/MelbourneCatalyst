"""Shared collector interface.

Every collector fetches from exactly one external source and returns
`RawTrendItem`s. Collectors should isolate *per-item* failures internally
(e.g. one bad subreddit or RSS feed shouldn't drop the rest of the batch —
see `reddit.py`/`rss.py`), but may let a *whole-source* failure (the API is
down, auth is misconfigured) propagate as an exception. The LangGraph node
wrapping each collector (`graph.py`) is the boundary that guarantees a
collection run as a whole never raises, and it's what records the error for
the `/sources` status endpoint — swallowing it here instead would hide it.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.agents.trend_analyzer.schemas import RawTrendItem

logger = logging.getLogger(__name__)


class Collector(Protocol):
    """A single-source trend collector."""

    async def collect(self) -> list[RawTrendItem]:
        """Fetch and normalize trend items. Never raises."""
        ...
