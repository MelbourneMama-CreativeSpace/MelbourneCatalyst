"""Tests for Claude-powered trend enrichment."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.agents.trend_analyzer import enrichment
from app.agents.trend_analyzer.schemas import RawTrendItem, TrendSource


def _item(title: str) -> RawTrendItem:
    return RawTrendItem(
        source=TrendSource.RSS,
        title=title,
        url=f"https://example.com/{title}",
        discovered_at=datetime.now(timezone.utc),
    )


async def test_enrich_items_returns_empty_for_no_items():
    assert await enrichment.enrich_items([]) == []


async def test_enrich_items_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(enrichment.settings, "ANTHROPIC_API_KEY", "")

    result = await enrichment.enrich_items([_item("A")])

    assert result[0].category == enrichment._FALLBACK_CATEGORY
    assert result[0].insight == ""


async def test_enrich_items_maps_tool_use_results_by_index(monkeypatch):
    monkeypatch.setattr(enrichment.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use_block = SimpleNamespace(
        type="tool_use",
        input={
            "results": [
                {"index": 0, "category": "marketing", "insight": "Relevant to campaigns"},
                {"index": 1, "category": "technology", "insight": "Emerging tech shift"},
            ]
        },
    )
    fake_response = SimpleNamespace(content=[tool_use_block])

    class _FakeMessages:
        async def create(self, **kwargs):
            return fake_response

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(enrichment, "_client", lambda: _FakeClient())

    result = await enrichment.enrich_items([_item("A"), _item("B")])

    assert [r.category for r in result] == ["marketing", "technology"]
    assert result[0].insight == "Relevant to campaigns"


async def test_enrich_items_falls_back_on_batch_failure(monkeypatch):
    monkeypatch.setattr(enrichment.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(enrichment, "_client", lambda: _FailingClient())

    result = await enrichment.enrich_items([_item("A")])

    assert result[0].category == enrichment._FALLBACK_CATEGORY
