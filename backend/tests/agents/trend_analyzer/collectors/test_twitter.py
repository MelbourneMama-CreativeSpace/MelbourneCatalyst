"""Tests for the X (Twitter) collector."""

from __future__ import annotations

import httpx
import respx

from app.agents.trend_analyzer.collectors.twitter import TwitterCollector

_SAMPLE_RESPONSE = {
    "data": [
        {
            "id": "1234567890",
            "text": "Marketing trends are shifting fast in 2026",
            "author_id": "42",
            "public_metrics": {
                "like_count": 100,
                "retweet_count": 20,
                "reply_count": 5,
                "quote_count": 1,
            },
        }
    ],
    "includes": {"users": [{"id": "42", "username": "marketer"}]},
}


async def test_collect_skips_when_no_bearer_token():
    items = await TwitterCollector(bearer_token="", queries=["marketing"]).collect()
    assert items == []


@respx.mock
async def test_collect_parses_tweets_into_raw_trend_items():
    respx.get("https://api.x.com/2/tweets/search/recent").mock(
        return_value=httpx.Response(200, json=_SAMPLE_RESPONSE)
    )

    items = await TwitterCollector(bearer_token="test-token", queries=["marketing trends"]).collect()

    assert len(items) == 1
    item = items[0]
    assert item.title == "Marketing trends are shifting fast in 2026"
    assert item.url == "https://x.com/marketer/status/1234567890"
    assert item.score == 125.0  # like + retweet + reply
    assert item.raw_metadata["query"] == "marketing trends"


@respx.mock
async def test_collect_isolates_a_failing_query():
    route = respx.get("https://api.x.com/2/tweets/search/recent")
    route.side_effect = [httpx.Response(500), httpx.Response(200, json=_SAMPLE_RESPONSE)]

    items = await TwitterCollector(
        bearer_token="test-token", queries=["bad query", "marketing trends"]
    ).collect()

    assert len(items) == 1
