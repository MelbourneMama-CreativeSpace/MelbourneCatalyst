"""Reddit collector — top daily posts from configured subreddits via PRAW,
in OAuth "read-only" (application-only, client-credentials) mode.

Originally built against Reddit's public `.json` endpoints since they
needed no auth — but confirmed live (twice, in separate sessions) that
those endpoints now return `403 Blocked`, part of Reddit's post-2023
anti-scraping enforcement. PRAW's read-only mode uses OAuth application
credentials (a free Reddit "script" app registration, no user login) and
is Reddit's actual supported path for this.

PRAW is sync-only, so calls run via `asyncio.to_thread`, same pattern as
the Google Trends collector.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import praw

from app.agents.trend_analyzer.schemas import RawTrendItem, TrendSource
from app.config import settings

logger = logging.getLogger(__name__)

_USER_AGENT = "mmcs-trend-analyzer/0.2 (contact: collabs@melbournemama.org)"


class RedditCollector:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        subreddits: list[str] | None = None,
        limit: int = 10,
    ) -> None:
        self.client_id = client_id or settings.REDDIT_CLIENT_ID
        self.client_secret = client_secret or settings.REDDIT_CLIENT_SECRET
        self.subreddits = subreddits or settings.REDDIT_SUBREDDITS
        self.limit = limit

    async def collect(self) -> list[RawTrendItem]:
        if not self.client_id or not self.client_secret:
            logger.warning(
                "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not configured; skipping Reddit collection"
            )
            return []

        items: list[RawTrendItem] = []
        for subreddit in self.subreddits:
            try:
                items.extend(await asyncio.to_thread(self._collect_subreddit_sync, subreddit))
            except Exception:
                logger.exception("Reddit collection failed for r/%s", subreddit)
        return items

    def _collect_subreddit_sync(self, subreddit_name: str) -> list[RawTrendItem]:
        reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=_USER_AGENT,
        )
        reddit.read_only = True

        now = datetime.now(timezone.utc)
        return [
            RawTrendItem(
                source=TrendSource.REDDIT,
                title=post.title,
                url=f"https://reddit.com{post.permalink}",
                description=post.selftext or None,
                score=float(post.score),
                discovered_at=now,
                raw_metadata={"subreddit": subreddit_name, "num_comments": post.num_comments},
            )
            for post in reddit.subreddit(subreddit_name).top(time_filter="day", limit=self.limit)
        ]
