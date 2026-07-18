"""Tests for Claude-powered competitor name suggestions."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.competitor_research import suggestions


async def test_suggest_competitor_names_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(suggestions.settings, "ANTHROPIC_API_KEY", "")

    names, ok = await suggestions.suggest_competitor_names("context")

    assert ok is False
    assert names == []


async def test_suggest_competitor_names_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(suggestions.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(suggestions, "_client", lambda: _FailingClient())

    names, ok = await suggestions.suggest_competitor_names("context")

    assert ok is False
    assert names == []


async def test_suggest_competitor_names_parses_and_filters_names(monkeypatch):
    monkeypatch.setattr(suggestions.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(
        type="tool_use",
        input={"names": ["Rival Co", "", "  ", "Another Rival", 42]},
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(suggestions, "_client", lambda: _FakeClient())

    names, ok = await suggestions.suggest_competitor_names("company profile here")

    assert ok is True
    assert names == ["Rival Co", "Another Rival"]
