"""Tests for the Reddit collector."""

from __future__ import annotations

import httpx
import respx

from app.agents.trend_analyzer.collectors.reddit import RedditCollector

_SAMPLE_RESPONSE = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "AI marketing trends for 2026",
                    "permalink": "/r/marketing/comments/abc123/ai_marketing_trends/",
                    "score": 342,
                    "num_comments": 51,
                    "selftext": "",
                }
            }
        ]
    }
}


@respx.mock
async def test_collect_parses_posts_into_raw_trend_items():
    respx.get("https://www.reddit.com/r/marketing/top.json").mock(
        return_value=httpx.Response(200, json=_SAMPLE_RESPONSE)
    )

    items = await RedditCollector(subreddits=["marketing"]).collect()

    assert len(items) == 1
    item = items[0]
    assert item.title == "AI marketing trends for 2026"
    assert item.url == "https://reddit.com/r/marketing/comments/abc123/ai_marketing_trends/"
    assert item.score == 342.0
    assert item.raw_metadata["subreddit"] == "marketing"


@respx.mock
async def test_collect_isolates_a_failing_subreddit():
    respx.get("https://www.reddit.com/r/marketing/top.json").mock(
        return_value=httpx.Response(200, json=_SAMPLE_RESPONSE)
    )
    respx.get("https://www.reddit.com/r/badsubreddit/top.json").mock(return_value=httpx.Response(500))

    items = await RedditCollector(subreddits=["badsubreddit", "marketing"]).collect()

    assert len(items) == 1
    assert items[0].raw_metadata["subreddit"] == "marketing"
