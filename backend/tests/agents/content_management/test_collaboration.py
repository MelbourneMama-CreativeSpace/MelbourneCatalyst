"""Tests for Claude-powered brand collaboration ideation."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.content_management import collaboration


async def test_generate_collaboration_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(collaboration.settings, "ANTHROPIC_API_KEY", "")

    generated, ok = await collaboration.generate_collaboration("context")

    assert ok is False
    assert generated.ideas == []


async def test_generate_collaboration_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(collaboration.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(collaboration, "_client", lambda: _FailingClient())

    generated, ok = await collaboration.generate_collaboration("context")

    assert ok is False
    assert generated.ideas == []


def _fake_client_returning(ideas: list[dict]):
    tool_use = SimpleNamespace(type="tool_use", input={"ideas": ideas})

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    return lambda: _FakeClient()


async def test_generate_collaboration_parses_ideas(monkeypatch):
    monkeypatch.setattr(collaboration.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        collaboration,
        "_client",
        _fake_client_returning(
            [
                {
                    "collaborator_archetype": "Micro-influencer food bloggers, 5-20k followers",
                    "partnership_angle": "Free tasting + sourdough-making class in exchange for a post.",
                    "outreach_template": "Hi! We'd love to host you for a sourdough class...",
                    "priority": "high",
                    "rationale": "Strong audience overlap with our target demographic.",
                },
            ]
        ),
    )

    generated, ok = await collaboration.generate_collaboration("context")

    assert ok is True
    assert len(generated.ideas) == 1
    idea = generated.ideas[0]
    assert idea.collaborator_archetype.startswith("Micro-influencer")
    assert idea.priority == "high"


async def test_generate_collaboration_defaults_invalid_priority_to_medium(monkeypatch):
    monkeypatch.setattr(collaboration.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        collaboration,
        "_client",
        _fake_client_returning(
            [
                {
                    "collaborator_archetype": "Local food critics",
                    "partnership_angle": "Review swap.",
                    "outreach_template": "Hi there...",
                    "priority": "urgent",  # not one of low/medium/high
                },
            ]
        ),
    )

    generated, ok = await collaboration.generate_collaboration("context")

    assert ok is True
    assert generated.ideas[0].priority == "medium"


async def test_generate_collaboration_skips_malformed_ideas(monkeypatch):
    monkeypatch.setattr(collaboration.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        collaboration,
        "_client",
        _fake_client_returning(
            [
                {"collaborator_archetype": "Missing required fields"},  # malformed — should be skipped
                {
                    "collaborator_archetype": "Valid archetype",
                    "partnership_angle": "Valid angle.",
                    "outreach_template": "Valid template.",
                    "priority": "low",
                },
            ]
        ),
    )

    generated, ok = await collaboration.generate_collaboration("context")

    assert ok is True
    assert len(generated.ideas) == 1
    assert generated.ideas[0].collaborator_archetype == "Valid archetype"


async def test_generate_collaboration_caps_ideas_at_configured_max(monkeypatch):
    monkeypatch.setattr(collaboration.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(collaboration.settings, "COLLABORATION_MAX_IDEAS", 2)
    monkeypatch.setattr(
        collaboration,
        "_client",
        _fake_client_returning(
            [
                {
                    "collaborator_archetype": f"Archetype {i}",
                    "partnership_angle": "Angle.",
                    "outreach_template": "Template.",
                    "priority": "low",
                }
                for i in range(5)
            ]
        ),
    )

    generated, ok = await collaboration.generate_collaboration("context")

    assert ok is True
    assert len(generated.ideas) == 2
