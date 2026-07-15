"""Tests for the YouTube collector."""

from __future__ import annotations

import httpx
import respx

from app.agents.trend_analyzer.collectors.youtube import YouTubeCollector

_SAMPLE_RESPONSE = {
    "items": [
        {
            "id": {"videoId": "abc123"},
            "snippet": {
                "title": "Top marketing trends 2026",
                "description": "A deep dive",
                "channelTitle": "Marketing Channel",
            },
        }
    ]
}


async def test_collect_skips_when_no_api_key():
    items = await YouTubeCollector(api_key="", queries=["marketing"]).collect()
    assert items == []


@respx.mock
async def test_collect_parses_search_results():
    respx.get("https://www.googleapis.com/youtube/v3/search").mock(
        return_value=httpx.Response(200, json=_SAMPLE_RESPONSE)
    )

    items = await YouTubeCollector(api_key="test-key", queries=["marketing trends"]).collect()

    assert len(items) == 1
    assert items[0].url == "https://www.youtube.com/watch?v=abc123"
    assert items[0].raw_metadata["channel"] == "Marketing Channel"


@respx.mock
async def test_collect_isolates_a_failing_query():
    route = respx.get("https://www.googleapis.com/youtube/v3/search")
    route.side_effect = [httpx.Response(500), httpx.Response(200, json=_SAMPLE_RESPONSE)]

    items = await YouTubeCollector(api_key="test-key", queries=["bad query", "marketing trends"]).collect()

    assert len(items) == 1
