"""Google Trends collector — rising related search queries for configured
seed keywords, via `pytrends-modern`.

No API key required. `pytrends-modern` is a synchronous client (the async
variant requires a headless-browser `BrowserConfig`, overkill here), so the
network call runs in a worker thread via `asyncio.to_thread` to avoid
blocking the event loop.

Originally used `trending_searches()` (today's flat top-searches list), but
confirmed live that Google has moved/deprecated the whole legacy
"unofficial internal API" surface it depended on
(`hottrends/visualize/internal/data`, `api/dailytrends`,
`api/realtimetrends` all 404) — not just one endpoint. The `explore` API
behind `interest_over_time()`/`related_queries()` (the actual Trends UI's
own API) is still live and confirmed working. `related_queries()['rising']`
is arguably a *better* trend signal anyway: growth-scored terms related to
a topic you actually care about, not an undifferentiated firehose of
today's top searches — the same seed-keyword pattern the YouTube/X/TikTok
collectors already use.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from pytrends_modern import TrendReq

from app.agents.trend_analyzer.schemas import RawTrendItem, TrendSource
from app.config import settings

logger = logging.getLogger(__name__)


class GoogleTrendsCollector:
    def __init__(self, region: str | None = None, seed_keywords: list[str] | None = None) -> None:
        self.region = region if region is not None else settings.GOOGLE_TRENDS_REGION
        self.seed_keywords = seed_keywords or settings.GOOGLE_TRENDS_SEED_KEYWORDS

    async def collect(self) -> list[RawTrendItem]:
        items: list[RawTrendItem] = []
        for keyword in self.seed_keywords:
            try:
                items.extend(await asyncio.to_thread(self._collect_keyword_sync, keyword))
            except Exception:
                logger.exception("Google Trends collection failed for seed keyword %r", keyword)
        return items

    def _collect_keyword_sync(self, keyword: str) -> list[RawTrendItem]:
        pytrends = TrendReq(
            hl="en-US",
            tz=0,
            retries=3,
            backoff_factor=0.3,
            rotate_user_agent=True,
        )
        pytrends.build_payload(kw_list=[keyword], timeframe="now 7-d", geo=self.region)
        related = pytrends.related_queries()
        rising = related.get(keyword, {}).get("rising")
        if rising is None or rising.empty:
            return []

        now = datetime.now(timezone.utc)
        return [
            RawTrendItem(
                source=TrendSource.GOOGLE_TRENDS,
                title=row["query"],
                url=f"https://trends.google.com/trends/explore?q={row['query'].replace(' ', '+')}",
                score=_parse_growth_value(row["value"]),
                discovered_at=now,
                raw_metadata={"seed_keyword": keyword, "growth": row["value"]},
            )
            for _, row in rising.iterrows()
        ]


def _parse_growth_value(value: object) -> float:
    """`related_queries()`'s `value` column is normally a growth percentage,
    but Google represents extreme growth (>5000%) as the literal string
    "Breakout" instead of a number — treat that as the floor of that range."""
    if isinstance(value, str) and value.strip().lower() == "breakout":
        return 5000.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
