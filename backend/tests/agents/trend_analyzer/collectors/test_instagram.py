"""Tests for the Instagram collector."""

from __future__ import annotations

import httpx
import respx

from app.agents.trend_analyzer.collectors.instagram import InstagramCollector

_HASHTAG_SEARCH_RESPONSE = {"data": [{"id": "hashtag-123"}]}
_TOP_MEDIA_RESPONSE = {
    "data": [
        {
            "id": "media-1",
            "caption": "Loving the new marketing campaign #marketing",
            "permalink": "https://www.instagram.com/p/abc123/",
            "like_count": 50,
            "comments_count": 5,
            "media_type": "IMAGE",
        }
    ]
}


async def test_collect_skips_when_no_credentials():
    items = await InstagramCollector(
        access_token="", business_account_id="", hashtags=["marketing"]
    ).collect()
    assert items == []


@respx.mock
async def test_collect_parses_top_media_into_raw_trend_items():
    respx.get("https://graph.facebook.com/v21.0/ig_hashtag_search").mock(
        return_value=httpx.Response(200, json=_HASHTAG_SEARCH_RESPONSE)
    )
    respx.get("https://graph.facebook.com/v21.0/hashtag-123/top_media").mock(
        return_value=httpx.Response(200, json=_TOP_MEDIA_RESPONSE)
    )

    items = await InstagramCollector(
        access_token="test-token", business_account_id="ig-user-1", hashtags=["marketing"]
    ).collect()

    assert len(items) == 1
    item = items[0]
    assert item.title == "Loving the new marketing campaign #marketing"
    assert item.url == "https://www.instagram.com/p/abc123/"
    assert item.score == 55.0
    assert item.raw_metadata["hashtag"] == "marketing"


@respx.mock
async def test_collect_returns_empty_when_hashtag_not_found():
    respx.get("https://graph.facebook.com/v21.0/ig_hashtag_search").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    items = await InstagramCollector(
        access_token="test-token", business_account_id="ig-user-1", hashtags=["nonexistent"]
    ).collect()

    assert items == []


@respx.mock
async def test_collect_isolates_a_failing_hashtag():
    respx.get("https://graph.facebook.com/v21.0/ig_hashtag_search").mock(
        side_effect=[httpx.Response(500), httpx.Response(200, json=_HASHTAG_SEARCH_RESPONSE)]
    )
    respx.get("https://graph.facebook.com/v21.0/hashtag-123/top_media").mock(
        return_value=httpx.Response(200, json=_TOP_MEDIA_RESPONSE)
    )

    items = await InstagramCollector(
        access_token="test-token",
        business_account_id="ig-user-1",
        hashtags=["badhashtag", "marketing"],
    ).collect()

    assert len(items) == 1
