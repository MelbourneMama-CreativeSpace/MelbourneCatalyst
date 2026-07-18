"""Tests for Claude-powered campaign generation."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.agents.content_management import campaign


async def test_generate_campaign_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(campaign.settings, "ANTHROPIC_API_KEY", "")

    generated, ok = await campaign.generate_campaign("some context")

    assert ok is False
    assert generated.name is None


async def test_generate_campaign_parses_tool_use_result(monkeypatch):
    monkeypatch.setattr(campaign.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(
        type="tool_use",
        input={
            "name": "Sourdough Summer Push",
            "objective": "Drive foot traffic during the sourdough trend spike.",
            "budget_allocation": "60% Instagram, 40% local partnerships.",
            "success_metrics": "Foot traffic, Instagram engagement rate.",
            "start_date": "2026-07-20",
            "end_date": "2026-08-03",
        },
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(campaign, "_client", lambda: _FakeClient())

    generated, ok = await campaign.generate_campaign("company profile + strategy + calendar here")

    assert ok is True
    assert generated.name == "Sourdough Summer Push"
    assert generated.start_date == date(2026, 7, 20)
    assert generated.end_date == date(2026, 8, 3)


async def test_generate_campaign_handles_missing_or_malformed_dates(monkeypatch):
    monkeypatch.setattr(campaign.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(
        type="tool_use",
        input={
            "name": "No dates given",
            "objective": "Objective only.",
            "start_date": "not-a-date",
        },
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(campaign, "_client", lambda: _FakeClient())

    generated, ok = await campaign.generate_campaign("context")

    assert ok is True
    assert generated.start_date is None
    assert generated.end_date is None


async def test_generate_campaign_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(campaign.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(campaign, "_client", lambda: _FailingClient())

    generated, ok = await campaign.generate_campaign("context")

    assert ok is False
    assert generated.name is None
