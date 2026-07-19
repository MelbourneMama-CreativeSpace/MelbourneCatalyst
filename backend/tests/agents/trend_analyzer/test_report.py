"""Tests for Claude-powered trend report generation."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.trend_analyzer import report


async def test_generate_trend_report_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(report.settings, "ANTHROPIC_API_KEY", "")

    generated, ok = await report.generate_trend_report("some context")

    assert ok is False
    assert generated.summary is None
    assert generated.key_themes == []


async def test_generate_trend_report_parses_tool_use_result(monkeypatch):
    monkeypatch.setattr(report.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(
        type="tool_use",
        input={
            "summary": "AI-native marketing tools are trending hard this week.",
            "key_themes": ["AI automation", "short-form video"],
            "notable_trends_summary": "Several viral posts about AI copywriting tools.",
            "content_opportunities": "Post a behind-the-scenes AI workflow video.",
        },
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(report, "_client", lambda: _FakeClient())

    generated, ok = await report.generate_trend_report("company profile + trends here")

    assert ok is True
    assert generated.summary.startswith("AI-native")
    assert generated.key_themes == ["AI automation", "short-form video"]
    assert generated.content_opportunities == "Post a behind-the-scenes AI workflow video."


async def test_generate_trend_report_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(report.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(report, "_client", lambda: _FailingClient())

    generated, ok = await report.generate_trend_report("context")

    assert ok is False
    assert generated.summary is None
