"""Tests for the Claude-powered Content Opportunity Discovery generator."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.trend_analyzer import opportunities


async def test_generate_content_opportunities_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(opportunities.settings, "ANTHROPIC_API_KEY", "")

    result, ok = await opportunities.generate_content_opportunities("some context")

    assert ok is False
    assert result == []


async def test_generate_content_opportunities_parses_a_successful_result(monkeypatch):
    monkeypatch.setattr(opportunities.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(
        type="tool_use",
        input={
            "opportunities": [
                {
                    "title": "Post about AI marketing tools",
                    "reasoning": "This trend is highly relevant to this company's audience.",
                    "source": "trend",
                    "priority": "high",
                },
                {
                    "title": "Christmas gift guide",
                    "reasoning": "Christmas falls within the planning window.",
                    "source": "seasonal",
                    "priority": "medium",
                },
            ]
        },
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(opportunities, "_client", lambda: _FakeClient())

    result, ok = await opportunities.generate_content_opportunities("real context")

    assert ok is True
    assert len(result) == 2
    assert result[0].title == "Post about AI marketing tools"
    assert result[0].source == "trend"
    assert result[0].priority == "high"
    assert result[1].source == "seasonal"


async def test_generate_content_opportunities_skips_malformed_items(monkeypatch):
    monkeypatch.setattr(opportunities.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(
        type="tool_use",
        input={
            "opportunities": [
                {"title": "Missing reasoning field", "source": "trend", "priority": "high"},
                {
                    "title": "Valid one",
                    "reasoning": "Real reason.",
                    "source": "evergreen",
                    "priority": "low",
                },
            ]
        },
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(opportunities, "_client", lambda: _FakeClient())

    result, ok = await opportunities.generate_content_opportunities("context")

    assert ok is True
    assert len(result) == 1
    assert result[0].title == "Valid one"


async def test_generate_content_opportunities_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(opportunities.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(opportunities, "_client", lambda: _FailingClient())

    result, ok = await opportunities.generate_content_opportunities("context")

    assert ok is False
    assert result == []
