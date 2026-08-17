"""TikTok collector — recent public videos matching the active niche via the
TikTok Research API.

Requires `TIKTOK_CLIENT_KEY`/`TIKTOK_CLIENT_SECRET`. Note: the Research API
is gated behind academic/institutional approval, not a standard developer
signup — most teams cannot get access to it at all. Built to the documented
contract regardless, and skips collection (with a warning, not an error)
when credentials are unset, same as the other collectors.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.agents.trend_analyzer.niche import resolve_niche_keywords
from app.agents.trend_analyzer.schemas import RawTrendItem, TrendSource
from app.config import settings

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
_QUERY_URL = "https://open.tiktokapis.com/v2/research/video/query/"
_FIELDS = (
    "id,video_description,create_time,region_code,"
    "share_count,view_count,like_count,comment_count,username"
)


class TikTokCollector:
    def __init__(
        self,
        client_key: str | None = None,
        client_secret: str | None = None,
        keywords: list[str] | None = None,
        max_count: int = 20,
    ) -> None:
        self.client_key = client_key or settings.TIKTOK_CLIENT_KEY
        self.client_secret = client_secret or settings.TIKTOK_CLIENT_SECRET
        # None means "resolve from the onboarded companies' niche at collect
        # time" (see `trend_analyzer/niche.py`); an explicit list overrides.
        self.keywords = keywords
        self.max_count = max_count

    async def collect(self) -> list[RawTrendItem]:
        if not self.client_key or not self.client_secret:
            logger.warning(
                "TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET not configured; skipping TikTok collection"
            )
            return []

        keywords = self.keywords if self.keywords is not None else await resolve_niche_keywords()
        if not keywords:
            return []

        async with httpx.AsyncClient(timeout=15.0) as client:
            access_token = await self._get_access_token(client)
            items: list[RawTrendItem] = []
            for keyword in keywords:
                try:
                    items.extend(await self._collect_keyword(client, access_token, keyword))
                except Exception:
                    logger.exception("TikTok collection failed for keyword %r", keyword)
            return items

    async def _get_access_token(self, client: httpx.AsyncClient) -> str:
        response = await client.post(
            _TOKEN_URL,
            data={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()
        return response.json()["access_token"]

    async def _collect_keyword(
        self, client: httpx.AsyncClient, access_token: str, keyword: str
    ) -> list[RawTrendItem]:
        now = datetime.now(timezone.utc)
        response = await client.post(
            _QUERY_URL,
            params={"fields": _FIELDS},
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "query": {
                    "and": [
                        {"operation": "IN", "field_name": "keyword", "field_values": [keyword]}
                    ]
                },
                "start_date": (now - timedelta(days=7)).strftime("%Y%m%d"),
                "end_date": now.strftime("%Y%m%d"),
                "max_count": self.max_count,
            },
        )
        response.raise_for_status()
        videos = response.json().get("data", {}).get("videos", [])

        return [
            RawTrendItem(
                source=TrendSource.TIKTOK,
                title=(video.get("video_description") or "TikTok video")[:280],
                url=f"https://www.tiktok.com/@{video.get('username', 'i')}/video/{video['id']}",
                score=float(
                    video.get("like_count", 0)
                    + video.get("share_count", 0)
                    + video.get("comment_count", 0)
                ),
                discovered_at=now,
                raw_metadata={"keyword": keyword, "region_code": video.get("region_code")},
            )
            for video in videos
        ]
