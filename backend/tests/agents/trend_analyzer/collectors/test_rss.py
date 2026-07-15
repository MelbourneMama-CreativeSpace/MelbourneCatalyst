"""Tests for the RSS/news feed collector."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.trend_analyzer.collectors import rss as rss_module
from app.agents.trend_analyzer.collectors.rss import RSSCollector


def _fake_parsed(entries: list[dict], feed_title: str = "Example Feed") -> SimpleNamespace:
    return SimpleNamespace(entries=entries, feed={"title": feed_title})


async def test_collect_parses_feed_entries(monkeypatch):
    parsed = _fake_parsed(
        [{"title": "New marketing tool launches", "link": "https://example.com/a", "summary": "..."}]
    )
    monkeypatch.setattr(rss_module.feedparser, "parse", lambda url: parsed)

    items = await RSSCollector(feed_urls=["https://example.com/feed"]).collect()

    assert len(items) == 1
    assert items[0].title == "New marketing tool launches"
    assert items[0].url == "https://example.com/a"
    assert items[0].raw_metadata["feed_title"] == "Example Feed"


async def test_collect_skips_entries_without_a_link(monkeypatch):
    parsed = _fake_parsed([{"title": "No link here"}])
    monkeypatch.setattr(rss_module.feedparser, "parse", lambda url: parsed)

    items = await RSSCollector(feed_urls=["https://example.com/feed"]).collect()

    assert items == []


async def test_collect_isolates_a_failing_feed(monkeypatch):
    def fake_parse(url: str):
        if url == "https://bad.example.com/feed":
            raise ValueError("boom")
        return _fake_parsed([{"title": "OK", "link": "https://example.com/ok"}])

    monkeypatch.setattr(rss_module.feedparser, "parse", fake_parse)

    items = await RSSCollector(
        feed_urls=["https://bad.example.com/feed", "https://example.com/feed"]
    ).collect()

    assert len(items) == 1
    assert items[0].url == "https://example.com/ok"
