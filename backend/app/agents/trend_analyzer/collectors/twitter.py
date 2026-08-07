"""X (Twitter) collector — recent posts matching configured search queries
via the X API v2 recent-search endpoint.

Requires `TWITTER_BEARER_TOKEN` from a paid X API developer tier — the free
tier cannot search. Skips collection (with a warning, not an error) when
unset, same as the YouTube collector.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.agents.trend_analyzer.niche import resolve_niche_keywords
from app.agents.trend_analyzer.schemas import RawTrendItem, TrendSource
from app.config import settings

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"


class TwitterCollector:
    def __init__(
        self,
        bearer_token: str | None = None,
        queries: list[str] | None = None,
        max_results: int = 25,
    ) -> None:
        self.bearer_token = bearer_token or settings.TWITTER_BEARER_TOKEN
        # None means "resolve from the onboarded companies' niche at collect
        # time" (see `trend_analyzer/niche.py`); an explicit list overrides.
        self.queries = queries
        self.max_results = max_results

    async def collect(self) -> list[RawTrendItem]:
        if not self.bearer_token:
            logger.warning("TWITTER_BEARER_TOKEN not configured; skipping X/Twitter collection")
            return []

        queries = self.queries if self.queries is not None else await resolve_niche_keywords()
        if not queries:
            return []

        items: list[RawTrendItem] = []
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            for query in queries:
                try:
                    items.extend(await self._collect_query(client, query))
                except Exception:
                    logger.exception("X/Twitter collection failed for query %r", query)
        return items

    async def _collect_query(self, client: httpx.AsyncClient, query: str) -> list[RawTrendItem]:
        response = await client.get(
            _SEARCH_URL,
            params={
                "query": query,
                "max_results": self.max_results,
                "tweet.fields": "public_metrics,created_at,author_id",
                "expansions": "author_id",
                "user.fields": "username",
            },
        )
        response.raise_for_status()
        payload = response.json()

        usernames_by_id = {
            user["id"]: user["username"] for user in payload.get("includes", {}).get("users", [])
        }
        now = datetime.now(timezone.utc)

        items = []
        for tweet in payload.get("data", []):
            metrics = tweet.get("public_metrics", {})
            username = usernames_by_id.get(tweet.get("author_id"), "i")
            items.append(
                RawTrendItem(
                    source=TrendSource.TWITTER,
                    title=tweet["text"],
                    url=f"https://x.com/{username}/status/{tweet['id']}",
                    score=float(
                        metrics.get("like_count", 0)
                        + metrics.get("retweet_count", 0)
                        + metrics.get("reply_count", 0)
                    ),
                    discovered_at=now,
                    raw_metadata={"query": query, "metrics": metrics},
                )
            )
        return items
