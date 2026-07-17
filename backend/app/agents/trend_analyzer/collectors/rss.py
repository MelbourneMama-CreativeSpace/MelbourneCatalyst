"""RSS/news feed collector — recent entries from a configured list of feed URLs.

`feedparser` is synchronous, so parsing runs in a worker thread.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import feedparser

from app.agents.trend_analyzer.schemas import RawTrendItem, TrendSource
from app.config import settings

logger = logging.getLogger(__name__)


class RSSCollector:
    def __init__(self, feed_urls: list[str] | None = None, limit_per_feed: int = 15) -> None:
        self.feed_urls = feed_urls or settings.RSS_FEED_URLS
        self.limit_per_feed = limit_per_feed

    async def collect(self) -> list[RawTrendItem]:
        items: list[RawTrendItem] = []
        for feed_url in self.feed_urls:
            try:
                items.extend(await asyncio.to_thread(self._collect_feed, feed_url))
            except Exception:
                logger.exception("RSS collection failed for %s", feed_url)
        return items

    def _collect_feed(self, feed_url: str) -> list[RawTrendItem]:
        parsed = feedparser.parse(feed_url)
        now = datetime.now(timezone.utc)
        items: list[RawTrendItem] = []

        for entry in parsed.entries[: self.limit_per_feed]:
            link = entry.get("link")
            if not link:
                continue
            items.append(
                RawTrendItem(
                    source=TrendSource.RSS,
                    title=entry.get("title", "Untitled"),
                    url=link,
                    description=entry.get("summary"),
                    discovered_at=now,
                    raw_metadata={
                        "feed_url": feed_url,
                        "feed_title": parsed.feed.get("title"),
                    },
                )
            )
        return items
