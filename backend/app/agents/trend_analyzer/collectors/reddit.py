"""Reddit collector — top daily posts from the subreddits matching the
active niche, via PRAW in OAuth "read-only" (application-only,
client-credentials) mode.

Unlike every other collector, this one can't use the niche keywords
directly: "handmade ceramics" is a search phrase, not a subreddit, and
`r/handmade ceramics` doesn't exist. So the keywords are first run through
Reddit's own subreddit search to discover real communities, and those are
what get polled. Discovery happens per collection run rather than being
cached, which keeps it correct when a company re-onboards into a different
niche — the extra calls are a handful per run, dwarfed by the post fetches.

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

from app.agents.trend_analyzer.niche import resolve_niche_keywords
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
        subreddits_per_keyword: int | None = None,
    ) -> None:
        self.client_id = client_id or settings.REDDIT_CLIENT_ID
        self.client_secret = client_secret or settings.REDDIT_CLIENT_SECRET
        # None means "discover from the onboarded companies' niche at
        # collect time"; an explicit list skips discovery (used by tests).
        self.subreddits = subreddits
        self.limit = limit
        self.subreddits_per_keyword = (
            subreddits_per_keyword
            if subreddits_per_keyword is not None
            else settings.REDDIT_SUBREDDITS_PER_KEYWORD
        )

    async def collect(self) -> list[RawTrendItem]:
        if not self.client_id or not self.client_secret:
            logger.warning(
                "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not configured; skipping Reddit collection"
            )
            return []

        subreddits = self.subreddits
        if subreddits is None:
            keywords = await resolve_niche_keywords()
            if not keywords:
                return []
            subreddits = await asyncio.to_thread(self._discover_subreddits_sync, keywords)
            if not subreddits:
                logger.warning("Reddit subreddit search matched nothing for niche %r", keywords)
                return []

        items: list[RawTrendItem] = []
        for subreddit in subreddits:
            try:
                items.extend(await asyncio.to_thread(self._collect_subreddit_sync, subreddit))
            except Exception:
                logger.exception("Reddit collection failed for r/%s", subreddit)
        return items

    def _reddit(self) -> praw.Reddit:
        reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=_USER_AGENT,
        )
        reddit.read_only = True
        return reddit

    def _discover_subreddits_sync(self, keywords: list[str]) -> list[str]:
        """Niche keywords -> real subreddit names, via Reddit's own search.

        Per-keyword failures are isolated the same way per-subreddit ones
        are: one keyword that matches nothing (or errors) shouldn't cost the
        run every other keyword's communities.
        """
        reddit = self._reddit()
        names: list[str] = []
        seen: set[str] = set()
        for keyword in keywords:
            try:
                matches = reddit.subreddits.search(keyword, limit=self.subreddits_per_keyword)
                for subreddit in matches:
                    name = subreddit.display_name
                    if name.casefold() in seen:
                        continue
                    seen.add(name.casefold())
                    names.append(name)
            except Exception:
                logger.exception("Reddit subreddit search failed for keyword %r", keyword)
        return names

    def _collect_subreddit_sync(self, subreddit_name: str) -> list[RawTrendItem]:
        reddit = self._reddit()
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
