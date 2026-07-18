"""Tests for Claude-powered strategy generation."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.content_management import strategy


async def test_generate_strategy_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(strategy.settings, "ANTHROPIC_API_KEY", "")

    generated, ok = await strategy.generate_strategy("some context")

    assert ok is False
    assert generated.summary is None


async def test_generate_strategy_parses_tool_use_result(monkeypatch):
    monkeypatch.setattr(strategy.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(
        type="tool_use",
        input={
            "summary": "Lean into AI-native marketing automation for SMBs.",
            "marketing_strategy": "Position as the AI-first alternative to legacy tools.",
            "campaign_direction": "Short-form video showing the tool in action.",
            "growth_recommendations": "Double down on content marketing and SEO.",
            "business_suggestions": "Explore a freemium tier.",
        },
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(strategy, "_client", lambda: _FakeClient())

    generated, ok = await strategy.generate_strategy("company profile + trends here")

    assert ok is True
    assert generated.summary == "Lean into AI-native marketing automation for SMBs."
    assert generated.marketing_strategy.startswith("Position as")
    assert generated.business_suggestions == "Explore a freemium tier."


async def test_generate_strategy_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(strategy.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(strategy, "_client", lambda: _FailingClient())

    generated, ok = await strategy.generate_strategy("context")

    assert ok is False
    assert generated.summary is None
