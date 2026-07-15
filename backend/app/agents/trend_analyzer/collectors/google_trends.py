"""Google Trends collector — today's trending search terms via `pytrends-modern`.

No API key required. `pytrends-modern` is a synchronous client (the async
variant requires a headless-browser `BrowserConfig`, overkill here), so the
network call runs in a worker thread via `asyncio.to_thread` to avoid blocking
the event loop.

Uses `pytrends-modern` rather than the original `pytrends` package: `pytrends`
hasn't shipped a release since April 2023 and reliably breaks (HTTP 429s)
against Google's evolving anti-bot measures. `pytrends-modern` is a drop-in,
actively maintained fork with built-in retry/backoff and user-agent rotation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from pytrends_modern import TrendReq

from app.agents.trend_analyzer.schemas import RawTrendItem, TrendSource
from app.config import settings


class GoogleTrendsCollector:
    def __init__(self, region: str | None = None) -> None:
        self.region = region or settings.GOOGLE_TRENDS_REGION

    async def collect(self) -> list[RawTrendItem]:
        # Whole-source failures propagate to the graph node, which records
        # them for the /sources status endpoint (see collectors/base.py).
        return await asyncio.to_thread(self._collect_sync)

    def _collect_sync(self) -> list[RawTrendItem]:
        pytrends = TrendReq(
            hl="en-US",
            tz=0,
            retries=3,
            backoff_factor=0.3,
            rotate_user_agent=True,
        )
        trending = pytrends.trending_searches(pn=self.region)
        terms = trending[0].tolist()
        total = len(terms)
        now = datetime.now(timezone.utc)

        return [
            RawTrendItem(
                source=TrendSource.GOOGLE_TRENDS,
                title=term,
                url=f"https://trends.google.com/trends/explore?q={term.replace(' ', '+')}",
                score=float(total - rank),
                discovered_at=now,
                raw_metadata={"region": self.region, "rank": rank},
            )
            for rank, term in enumerate(terms)
        ]
