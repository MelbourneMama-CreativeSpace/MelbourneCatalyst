"""Tests for Claude-powered comparison generation."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.competitor_research import comparison


async def test_generate_comparison_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(comparison.settings, "ANTHROPIC_API_KEY", "")

    generated, ok = await comparison.generate_comparison("some context")

    assert ok is False
    assert generated.product_pricing_comparison is None


async def test_generate_comparison_parses_tool_use_result(monkeypatch):
    monkeypatch.setattr(comparison.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(
        type="tool_use",
        input={
            "product_pricing_comparison": "Both offer subscription pricing; competitor skews enterprise.",
            "marketing_strategy_analysis": "Competitor leans heavily on case studies.",
            "competitive_gaps": "No enterprise sales motion yet.",
            "strategic_recommendations": "Build an enterprise tier.",
        },
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(comparison, "_client", lambda: _FakeClient())

    generated, ok = await comparison.generate_comparison("company + competitor profiles here")

    assert ok is True
    assert generated.competitive_gaps == "No enterprise sales motion yet."
    assert generated.strategic_recommendations == "Build an enterprise tier."


async def test_generate_comparison_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(comparison.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(comparison, "_client", lambda: _FailingClient())

    generated, ok = await comparison.generate_comparison("context")

    assert ok is False
    assert generated.product_pricing_comparison is None
