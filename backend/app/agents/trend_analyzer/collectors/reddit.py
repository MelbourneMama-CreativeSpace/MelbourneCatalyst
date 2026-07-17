"""Reddit collector — top daily posts from configured subreddits via Reddit's
public read-only `.json` endpoints. No OAuth needed, but Reddit requires a
descriptive `User-Agent` or it will rate-limit/block the request.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.agents.trend_analyzer.schemas import RawTrendItem, TrendSource
from app.config import settings

logger = logging.getLogger(__name__)

_USER_AGENT = "mmcs-trend-analyzer/0.1 (contact: collabs@melbournemama.org)"


class RedditCollector:
    def __init__(self, subreddits: list[str] | None = None, limit: int = 10) -> None:
        self.subreddits = subreddits or settings.REDDIT_SUBREDDITS
        self.limit = limit

    async def collect(self) -> list[RawTrendItem]:
        items: list[RawTrendItem] = []
        async with httpx.AsyncClient(headers={"User-Agent": _USER_AGENT}, timeout=10.0) as client:
            for subreddit in self.subreddits:
                try:
                    items.extend(await self._collect_subreddit(client, subreddit))
                except Exception:
                    logger.exception("Reddit collection failed for r/%s", subreddit)
        return items

    async def _collect_subreddit(self, client: httpx.AsyncClient, subreddit: str) -> list[RawTrendItem]:
        response = await client.get(
            f"https://www.reddit.com/r/{subreddit}/top.json",
            params={"limit": self.limit, "t": "day"},
        )
        response.raise_for_status()
        posts = response.json()["data"]["children"]
        now = datetime.now(timezone.utc)

        return [
            RawTrendItem(
                source=TrendSource.REDDIT,
                title=post["data"]["title"],
                url=f"https://reddit.com{post['data']['permalink']}",
                description=post["data"].get("selftext") or None,
                score=float(post["data"].get("score", 0)),
                discovered_at=now,
                raw_metadata={
                    "subreddit": subreddit,
                    "num_comments": post["data"].get("num_comments"),
                },
            )
            for post in posts
        ]
