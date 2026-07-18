"""Tests for the Claude-powered company profile extractor."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.company_analyzer import extractor


async def test_extract_falls_back_to_empty_profile_without_api_key(monkeypatch):
    monkeypatch.setattr(extractor.settings, "ANTHROPIC_API_KEY", "")

    profile, extracted_ok = await extractor.extract_company_profile("some content")

    assert extracted_ok is False
    assert profile.name is None
    assert profile.niche_keywords == []


async def test_extract_parses_tool_use_result(monkeypatch):
    monkeypatch.setattr(extractor.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use = SimpleNamespace(
        type="tool_use",
        input={
            "name": "Example Co",
            "industry": "B2B SaaS",
            "business_model": "Subscription",
            "target_audience": "Marketing teams at 50-500 person companies",
            "brand_voice": "Confident, playful",
            "unique_value_prop": "AI-native from day one",
            "niche_keywords": ["marketing automation", "AI content", "campaign analytics"],
            "summary": "One-paragraph overview here.",
        },
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(extractor, "_client", lambda: _FakeClient())

    profile, extracted_ok = await extractor.extract_company_profile("website content here")

    assert extracted_ok is True
    assert profile.name == "Example Co"
    assert profile.industry == "B2B SaaS"
    assert profile.niche_keywords == ["marketing automation", "AI content", "campaign analytics"]
    assert profile.summary == "One-paragraph overview here."


async def test_extract_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(extractor.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(extractor, "_client", lambda: _FailingClient())

    profile, extracted_ok = await extractor.extract_company_profile("content")

    assert extracted_ok is False
    assert profile.name is None
    assert profile.niche_keywords == []
