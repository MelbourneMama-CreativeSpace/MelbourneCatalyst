"""Tests for Claude-powered Knowledge Base audit generation."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.knowledge_base import audit


async def test_generate_audit_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(audit.settings, "ANTHROPIC_API_KEY", "")

    generated, ok = await audit.generate_audit("some context")

    assert ok is False
    assert generated.coverage_summary is None


async def test_generate_audit_parses_tool_use_result(monkeypatch):
    monkeypatch.setattr(audit.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(
        type="tool_use",
        input={
            "coverage_summary": "The KB covers the homepage and about page.",
            "identified_gaps": "No pricing or product-detail content ingested yet.",
            "recommendations": "Ingest the pricing and product pages next.",
        },
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(audit, "_client", lambda: _FakeClient())

    generated, ok = await audit.generate_audit("company profile + document sample here")

    assert ok is True
    assert generated.coverage_summary.startswith("The KB covers")
    assert generated.identified_gaps == "No pricing or product-detail content ingested yet."


async def test_generate_audit_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(audit.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(audit, "_client", lambda: _FailingClient())

    generated, ok = await audit.generate_audit("context")

    assert ok is False
    assert generated.coverage_summary is None
