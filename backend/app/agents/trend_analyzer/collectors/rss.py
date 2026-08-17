"""RSS/news feed collector — recent entries from feeds built dynamically for
the active niche, plus any statically-configured feeds.

Unlike the other collectors, RSS doesn't have one canonical "search by
keyword" API to call — an RSS feed is a fixed URL. Google News publishes a
search-as-RSS endpoint (`news.google.com/rss/search?q=...`) that fills that
gap: one feed URL per niche keyword, built fresh from the onboarded
companies' extracted niche each run (see `trend_analyzer/niche.py`), the
same resolve-at-collect-time pattern the other collectors use. This is what
actually makes RSS company-specific — previously it only ever read whatever
fixed feed URLs sat in `.env` (e.g. TechCrunch), which had no relationship
to any onboarded company's niche at all.

`RSS_FEED_URLS` still works as an optional supplemental list of fixed feeds
(operator-curated industry publications, for example) layered on top of the
dynamic per-keyword ones — not a replacement for them.

`feedparser` is synchronous, so parsing runs in a worker thread.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser

from app.agents.trend_analyzer.niche import resolve_niche_keywords
from app.agents.trend_analyzer.schemas import RawTrendItem, TrendSource
from app.config import settings

logger = logging.getLogger(__name__)

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


def _google_news_feed_url(keyword: str) -> str:
    return _GOOGLE_NEWS_RSS.format(query=quote_plus(keyword))


class RSSCollector:
    def __init__(self, feed_urls: list[str] | None = None, limit_per_feed: int = 15) -> None:
        # None means "build dynamic per-niche-keyword feeds at collect time,
        # plus any statically-configured RSS_FEED_URLS"; an explicit list
        # skips both and uses exactly what's passed (used by tests).
        self.feed_urls = feed_urls
        self.limit_per_feed = limit_per_feed

    async def collect(self) -> list[RawTrendItem]:
        feed_urls = self.feed_urls
        if feed_urls is None:
            keywords = await resolve_niche_keywords()
            feed_urls = [_google_news_feed_url(kw) for kw in keywords] + list(
                settings.RSS_FEED_URLS
            )
            if not feed_urls:
                return []

        items: list[RawTrendItem] = []
        for feed_url in feed_urls:
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
