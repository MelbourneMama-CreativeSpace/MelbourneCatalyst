"""Tests for Composio-backed post publishing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.social_media_analyzer import publish


def _configure(monkeypatch, **overrides):
    monkeypatch.setattr(publish.settings, "COMPOSIO_API_KEY", "test-composio-key")
    monkeypatch.setattr(publish.settings, "COMPOSIO_LINKEDIN_AUTH_CONFIG_ID", "ac_linkedin_123")
    monkeypatch.setattr(
        publish.settings, "COMPOSIO_LINKEDIN_POST_TOOL_SLUG", "LINKEDIN_CREATE_LINKEDIN_POST"
    )
    for setting_name, value in overrides.items():
        monkeypatch.setattr(publish.settings, setting_name, value)


async def test_publish_post_raises_when_api_key_not_set(monkeypatch):
    _configure(monkeypatch, COMPOSIO_API_KEY="")

    with pytest.raises(publish.PublishNotConfiguredError):
        await publish.publish_post("linkedin", "conn-123", "hello world")


async def test_publish_post_raises_when_post_tool_slug_not_set(monkeypatch):
    # This is the real, current state of this environment — no post tool
    # slug has been confirmed against a live Composio account yet.
    _configure(monkeypatch, COMPOSIO_LINKEDIN_POST_TOOL_SLUG="")

    with pytest.raises(publish.PublishNotConfiguredError):
        await publish.publish_post("linkedin", "conn-123", "hello world")


async def test_publish_post_raises_for_unknown_platform(monkeypatch):
    _configure(monkeypatch)

    with pytest.raises(ValueError, match="Unknown platform"):
        await publish.publish_post("myspace", "conn-123", "hello world")


async def test_publish_post_calls_composio_execute_with_the_right_arguments(monkeypatch):
    _configure(monkeypatch)

    captured = {}

    class _FakeTools:
        def execute(self, tool_slug, **kwargs):
            captured["tool_slug"] = tool_slug
            captured["kwargs"] = kwargs
            return SimpleNamespace(id="exec-abc123")

    monkeypatch.setattr(publish, "_client", lambda: SimpleNamespace(tools=_FakeTools()))

    result = await publish.publish_post("linkedin", "conn-123", "A real ready-to-publish caption.")

    assert result == "exec-abc123"
    assert captured["tool_slug"] == "LINKEDIN_CREATE_LINKEDIN_POST"
    assert captured["kwargs"]["connected_account_id"] == "conn-123"
    assert captured["kwargs"]["arguments"] == {"text": "A real ready-to-publish caption."}


async def test_publish_post_propagates_a_real_composio_failure(monkeypatch):
    _configure(monkeypatch)

    class _FailingTools:
        def execute(self, tool_slug, **kwargs):
            raise RuntimeError("Composio: connected account is expired")

    monkeypatch.setattr(publish, "_client", lambda: SimpleNamespace(tools=_FailingTools()))

    with pytest.raises(RuntimeError, match="expired"):
        await publish.publish_post("linkedin", "conn-123", "text")
