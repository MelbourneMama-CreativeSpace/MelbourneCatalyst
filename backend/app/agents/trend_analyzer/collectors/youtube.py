"""YouTube collector — recent high-view videos matching configured search
queries via the YouTube Data API v3 REST endpoint.

Calls the REST API directly with `httpx` rather than depending on
`google-api-python-client`, which is sync-only and pulls in a heavy transitive
dependency tree (httplib2, google-auth, uritemplate, etc.) for what is just
one GET request — using it would mean this collector alone needs
`asyncio.to_thread` and a much larger install, unlike every other collector
here. Requires `YOUTUBE_API_KEY`; skips collection (with a warning, not an
error) when unset.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.agents.trend_analyzer.niche import resolve_niche_keywords
from app.agents.trend_analyzer.schemas import RawTrendItem, TrendSource
from app.config import settings

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


class YouTubeCollector:
    def __init__(
        self,
        api_key: str | None = None,
        queries: list[str] | None = None,
        max_results: int = 10,
    ) -> None:
        self.api_key = api_key or settings.YOUTUBE_API_KEY
        # None means "resolve from the onboarded companies' niche at collect
        # time" (see `trend_analyzer/niche.py`); an explicit list overrides.
        self.queries = queries
        self.max_results = max_results

    async def collect(self) -> list[RawTrendItem]:
        if not self.api_key:
            logger.warning("YOUTUBE_API_KEY not configured; skipping YouTube collection")
            return []

        queries = self.queries if self.queries is not None else await resolve_niche_keywords()
        if not queries:
            return []

        published_after = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        items: list[RawTrendItem] = []

        async with httpx.AsyncClient(timeout=10.0) as client:
            for query in queries:
                try:
                    items.extend(await self._collect_query(client, query, published_after))
                except Exception:
                    logger.exception("YouTube collection failed for query %r", query)
        return items

    async def _collect_query(
        self, client: httpx.AsyncClient, query: str, published_after: str
    ) -> list[RawTrendItem]:
        response = await client.get(
            _SEARCH_URL,
            params={
                "key": self.api_key,
                "q": query,
                "part": "snippet",
                "type": "video",
                "order": "viewCount",
                "publishedAfter": published_after,
                "maxResults": self.max_results,
            },
        )
        response.raise_for_status()
        now = datetime.now(timezone.utc)

        return [
            RawTrendItem(
                source=TrendSource.YOUTUBE,
                title=video["snippet"]["title"],
                url=f"https://www.youtube.com/watch?v={video['id']['videoId']}",
                description=video["snippet"].get("description"),
                discovered_at=now,
                raw_metadata={"query": query, "channel": video["snippet"].get("channelTitle")},
            )
            for video in response.json().get("items", [])
        ]
