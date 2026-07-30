"""Tests for the Claude-powered performance insights generator."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.social_media_analyzer import insights


async def test_generate_performance_insights_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(insights.settings, "ANTHROPIC_API_KEY", "")

    result, ok = await insights.generate_performance_insights("some context")

    assert ok is False
    assert result is None


async def test_generate_performance_insights_parses_a_successful_result(monkeypatch):
    monkeypatch.setattr(insights.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(
        type="tool_use",
        input={"insights": "Engagement is trending up on LinkedIn; post more there."},
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            # The context, including the "not enough data" instruction,
            # should reach Claude via the system prompt — confirm the
            # call actually carries the real context, not a stub.
            assert "some real context" in kwargs["messages"][0]["content"]
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(insights, "_client", lambda: _FakeClient())

    result, ok = await insights.generate_performance_insights("some real context")

    assert ok is True
    assert result == "Engagement is trending up on LinkedIn; post more there."


async def test_generate_performance_insights_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(insights.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(insights, "_client", lambda: _FailingClient())

    result, ok = await insights.generate_performance_insights("context")

    assert ok is False
    assert result is None


def test_system_prompt_instructs_claude_not_to_fabricate_thin_data():
    assert "not enough data" in insights._SYSTEM_PROMPT.lower()
    assert "never speculate" in insights._SYSTEM_PROMPT.lower()
