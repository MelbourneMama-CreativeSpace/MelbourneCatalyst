"""Tests for the Claude-powered Creative Brief Generator."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.content_management import creative_brief


async def test_generate_creative_brief_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(creative_brief.settings, "ANTHROPIC_API_KEY", "")

    result, ok = await creative_brief.generate_creative_brief(
        "context", "Title", "Description", "instagram", "reel"
    )

    assert ok is False
    assert result.hook is None
    assert result.shot_list == []


async def test_generate_creative_brief_parses_a_successful_result(monkeypatch):
    monkeypatch.setattr(creative_brief.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(
        type="tool_use",
        input={
            "hook": "Open on a close-up of the product.",
            "shot_list": ["Wide establishing shot", "Close-up on hands", "Reaction shot"],
            "visual_references": "Warm, natural light; handheld camera feel.",
            "editing_notes": "Fast cuts on the beat, captions burned in.",
            "thumbnail_concept": "Bold text over a freeze-frame of the reaction.",
        },
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(creative_brief, "_client", lambda: _FakeClient())

    result, ok = await creative_brief.generate_creative_brief(
        "context", "Title", "Description", "instagram", "reel"
    )

    assert ok is True
    assert result.hook == "Open on a close-up of the product."
    assert len(result.shot_list) == 3
    assert result.thumbnail_concept == "Bold text over a freeze-frame of the reaction."


async def test_generate_creative_brief_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(creative_brief.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(creative_brief, "_client", lambda: _FailingClient())

    result, ok = await creative_brief.generate_creative_brief(
        "context", "Title", "Description", "instagram", "reel"
    )

    assert ok is False
    assert result.hook is None
