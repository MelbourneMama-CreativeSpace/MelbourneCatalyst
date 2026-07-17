"""Tests for the TikTok collector."""

from __future__ import annotations

import httpx
import respx

from app.agents.trend_analyzer.collectors.tiktok import TikTokCollector

_TOKEN_RESPONSE = {"access_token": "fake-access-token", "expires_in": 7200, "token_type": "Bearer"}
_QUERY_RESPONSE = {
    "data": {
        "videos": [
            {
                "id": 987654321,
                "video_description": "Latest social media marketing hacks",
                "region_code": "US",
                "share_count": 10,
                "view_count": 1000,
                "like_count": 200,
                "comment_count": 15,
                "username": "creator1",
            }
        ],
        "has_more": False,
    }
}


async def test_collect_skips_when_no_credentials():
    items = await TikTokCollector(client_key="", client_secret="", keywords=["marketing"]).collect()
    assert items == []


@respx.mock
async def test_collect_parses_videos_into_raw_trend_items():
    respx.post("https://open.tiktokapis.com/v2/oauth/token/").mock(
        return_value=httpx.Response(200, json=_TOKEN_RESPONSE)
    )
    respx.post("https://open.tiktokapis.com/v2/research/video/query/").mock(
        return_value=httpx.Response(200, json=_QUERY_RESPONSE)
    )

    items = await TikTokCollector(
        client_key="key", client_secret="secret", keywords=["marketing trends"]
    ).collect()

    assert len(items) == 1
    item = items[0]
    assert item.title == "Latest social media marketing hacks"
    assert item.url == "https://www.tiktok.com/@creator1/video/987654321"
    assert item.score == 225.0  # like + share + comment
    assert item.raw_metadata["region_code"] == "US"


@respx.mock
async def test_collect_isolates_a_failing_keyword():
    respx.post("https://open.tiktokapis.com/v2/oauth/token/").mock(
        return_value=httpx.Response(200, json=_TOKEN_RESPONSE)
    )
    route = respx.post("https://open.tiktokapis.com/v2/research/video/query/")
    route.side_effect = [httpx.Response(500), httpx.Response(200, json=_QUERY_RESPONSE)]

    items = await TikTokCollector(
        client_key="key", client_secret="secret", keywords=["bad keyword", "marketing trends"]
    ).collect()

    assert len(items) == 1
