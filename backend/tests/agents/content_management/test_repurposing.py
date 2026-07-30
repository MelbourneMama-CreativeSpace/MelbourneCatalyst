"""Tests for the Claude-powered Content Repurposing Engine."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.content_management import repurposing


async def test_repurpose_content_item_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(repurposing.settings, "ANTHROPIC_API_KEY", "")

    result, ok = await repurposing.repurpose_content_item(
        "context", "Original title", "Original copy.", "instagram", "story"
    )

    assert ok is False
    assert result is None


async def test_repurpose_content_item_parses_a_successful_result(monkeypatch):
    monkeypatch.setattr(repurposing.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(
        type="tool_use",
        input={
            "title": "Quick IG take",
            "description": "Same idea, punchier for Instagram.",
            "draft_copy": "Here's the short version →",
            "hashtags": ["smallbiz"],
        },
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(repurposing, "_client", lambda: _FakeClient())

    result, ok = await repurposing.repurpose_content_item(
        "context", "Original LinkedIn post", "A long professional take.", "instagram", "story"
    )

    assert ok is True
    assert result.title == "Quick IG take"
    assert result.platform == "instagram"
    assert result.content_type == "story"
    assert result.draft_copy == "Here's the short version →"
    assert result.hashtags == ["smallbiz"]


async def test_repurpose_content_item_falls_back_when_draft_copy_missing(monkeypatch):
    monkeypatch.setattr(repurposing.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(type="tool_use", input={"title": "t", "description": "d", "draft_copy": ""})

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(repurposing, "_client", lambda: _FakeClient())

    result, ok = await repurposing.repurpose_content_item(
        "context", "Title", "Copy.", "instagram", "story"
    )

    assert ok is False
    assert result is None


async def test_repurpose_content_item_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(repurposing.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(repurposing, "_client", lambda: _FailingClient())

    result, ok = await repurposing.repurpose_content_item(
        "context", "Title", "Copy.", "instagram", "story"
    )

    assert ok is False
    assert result is None
