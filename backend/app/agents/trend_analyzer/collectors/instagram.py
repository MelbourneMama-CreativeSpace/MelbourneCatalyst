"""Instagram collector — top media for configured hashtags via the Instagram
Graph API's hashtag search + top_media endpoints.

Requires a Business/Creator Instagram account behind a Meta app with hashtag
search permissions: `INSTAGRAM_ACCESS_TOKEN` (long-lived token) and
`INSTAGRAM_BUSINESS_ACCOUNT_ID`. Skips collection (with a warning, not an
error) when unset, same as the YouTube collector.

Hashtags are derived from the onboarded companies' niche (see
`trend_analyzer/niche.py`) rather than configured. Meta caps hashtag search
at 30 unique hashtags per Instagram account per rolling 7 days and every
run spends from that budget, which is why `TREND_NICHE_MAX_HASHTAGS`
defaults far below the general keyword cap.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from app.agents.trend_analyzer.niche import resolve_niche_keywords, to_hashtags
from app.agents.trend_analyzer.schemas import RawTrendItem, TrendSource
from app.config import settings

logger = logging.getLogger(__name__)

_GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
_MEDIA_FIELDS = "id,caption,permalink,like_count,comments_count,timestamp,media_type"


class InstagramCollector:
    def __init__(
        self,
        access_token: str | None = None,
        business_account_id: str | None = None,
        hashtags: list[str] | None = None,
        limit_per_hashtag: int = 10,
    ) -> None:
        self.access_token = access_token or settings.INSTAGRAM_ACCESS_TOKEN
        self.business_account_id = business_account_id or settings.INSTAGRAM_BUSINESS_ACCOUNT_ID
        # None means "derive from the onboarded companies' niche at collect
        # time" (see `trend_analyzer/niche.py`); an explicit list overrides.
        self.hashtags = hashtags
        self.limit_per_hashtag = limit_per_hashtag

    async def collect(self) -> list[RawTrendItem]:
        if not self.access_token or not self.business_account_id:
            logger.warning(
                "INSTAGRAM_ACCESS_TOKEN / INSTAGRAM_BUSINESS_ACCOUNT_ID not configured; "
                "skipping Instagram collection"
            )
            return []

        hashtags = (
            self.hashtags
            if self.hashtags is not None
            else to_hashtags(await resolve_niche_keywords())
        )
        if not hashtags:
            return []

        items: list[RawTrendItem] = []
        async with httpx.AsyncClient(timeout=10.0) as client:
            for hashtag in hashtags:
                try:
                    items.extend(await self._collect_hashtag(client, hashtag))
                except Exception:
                    logger.exception("Instagram collection failed for #%s", hashtag)
        return items

    async def _collect_hashtag(self, client: httpx.AsyncClient, hashtag: str) -> list[RawTrendItem]:
        search_response = await client.get(
            f"{_GRAPH_API_BASE}/ig_hashtag_search",
            params={
                "user_id": self.business_account_id,
                "q": hashtag,
                "access_token": self.access_token,
            },
        )
        search_response.raise_for_status()
        hashtag_results = search_response.json().get("data", [])
        if not hashtag_results:
            return []
        hashtag_id = hashtag_results[0]["id"]

        media_response = await client.get(
            f"{_GRAPH_API_BASE}/{hashtag_id}/top_media",
            params={
                "user_id": self.business_account_id,
                "fields": _MEDIA_FIELDS,
                "access_token": self.access_token,
            },
        )
        media_response.raise_for_status()
        now = datetime.now(timezone.utc)

        return [
            RawTrendItem(
                source=TrendSource.INSTAGRAM,
                title=(media.get("caption") or f"#{hashtag} post")[:280],
                url=media["permalink"],
                score=float(media.get("like_count", 0) + media.get("comments_count", 0)),
                discovered_at=now,
                raw_metadata={"hashtag": hashtag, "media_type": media.get("media_type")},
            )
            for media in media_response.json().get("data", [])[: self.limit_per_hashtag]
        ]
