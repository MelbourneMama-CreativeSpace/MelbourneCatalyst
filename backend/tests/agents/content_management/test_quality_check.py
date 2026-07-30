"""Tests for Claude-powered content quality + brand consistency review."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.content_management import quality_check


async def test_check_content_quality_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(quality_check.settings, "ANTHROPIC_API_KEY", "")

    result, ok = await quality_check.check_content_quality("some draft", "friendly", "linkedin")

    assert ok is False
    assert result.passed is None


async def test_check_content_quality_parses_a_passing_result(monkeypatch):
    monkeypatch.setattr(quality_check.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(
        type="tool_use", input={"passed": True, "issues": [], "notes": "Reads well, on-brand."}
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(quality_check, "_client", lambda: _FakeClient())

    result, ok = await quality_check.check_content_quality("Great draft copy.", "playful", "instagram")

    assert ok is True
    assert result.passed is True
    assert result.issues == []
    assert result.notes == "Reads well, on-brand."


async def test_check_content_quality_parses_a_failing_result_with_issues(monkeypatch):
    monkeypatch.setattr(quality_check.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(
        type="tool_use",
        input={
            "passed": False,
            "issues": ["Tone is too formal for Instagram.", "Missing a call to action."],
            "notes": "Needs a pass before publishing.",
        },
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(quality_check, "_client", lambda: _FakeClient())

    result, ok = await quality_check.check_content_quality("Draft.", "playful", "instagram")

    assert ok is True
    assert result.passed is False
    assert len(result.issues) == 2


async def test_check_content_quality_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(quality_check.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(quality_check, "_client", lambda: _FailingClient())

    result, ok = await quality_check.check_content_quality("Draft.", "playful", "instagram")

    assert ok is False
    assert result.passed is None
