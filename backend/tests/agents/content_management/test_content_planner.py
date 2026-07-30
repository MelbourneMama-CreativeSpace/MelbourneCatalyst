"""Tests for Claude-powered content plan generation."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from app.agents.content_management import content_planner


async def test_generate_content_plan_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(content_planner.settings, "ANTHROPIC_API_KEY", "")

    generated, ok = await content_planner.generate_content_plan("context", days=14)

    assert ok is False
    assert generated.items == []


async def test_generate_content_plan_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(content_planner.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(content_planner, "_client", lambda: _FailingClient())

    generated, ok = await content_planner.generate_content_plan("context", days=14)

    assert ok is False
    assert generated.items == []


def _fake_client_returning(items: list[dict]):
    tool_use = SimpleNamespace(type="tool_use", input={"items": items})

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    return lambda: _FakeClient()


async def test_generate_content_plan_converts_days_from_now_to_real_dates(monkeypatch):
    monkeypatch.setattr(content_planner.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        content_planner,
        "_client",
        _fake_client_returning(
            [
                {
                    "title": "AI marketing carousel",
                    "description": "5-slide carousel on AI-native marketing tools.",
                    "draft_copy": "Slide 1: Ever tried to keep up with AI marketing tools? Swipe →",
                    "content_type": "carousel",
                    "platform": "instagram",
                    "theme": "AI trends",
                    "days_from_now": 3,
                    "related_trend_title": "ai marketing tools",
                },
            ]
        ),
    )

    generated, ok = await content_planner.generate_content_plan("context", days=14)

    assert ok is True
    assert len(generated.items) == 1
    item = generated.items[0]
    assert item.title == "AI marketing carousel"
    assert item.suggested_date == date.today() + timedelta(days=3)
    assert item.related_trend_title == "ai marketing tools"
    assert item.draft_copy == "Slide 1: Ever tried to keep up with AI marketing tools? Swipe →"


async def test_generate_content_plan_clamps_days_from_now_to_valid_range(monkeypatch):
    monkeypatch.setattr(content_planner.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        content_planner,
        "_client",
        _fake_client_returning(
            [
                {
                    "title": "Too far out",
                    "description": "d",
                    "draft_copy": "dc",
                    "content_type": "post",
                    "platform": "linkedin",
                    "days_from_now": 999,
                },
                {
                    "title": "Negative",
                    "description": "d",
                    "draft_copy": "dc",
                    "content_type": "post",
                    "platform": "linkedin",
                    "days_from_now": -5,
                },
            ]
        ),
    )

    generated, ok = await content_planner.generate_content_plan("context", days=14)

    assert ok is True
    assert generated.items[0].suggested_date == date.today() + timedelta(days=13)  # clamped to days-1
    assert generated.items[1].suggested_date == date.today()  # clamped to 0


async def test_generate_content_plan_skips_malformed_items(monkeypatch):
    monkeypatch.setattr(content_planner.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        content_planner,
        "_client",
        _fake_client_returning(
            [
                {"title": "Missing required fields"},  # malformed — should be skipped
                {
                    "title": "Valid item",
                    "description": "d",
                    "draft_copy": "dc",
                    "content_type": "post",
                    "platform": "linkedin",
                    "days_from_now": 1,
                },
            ]
        ),
    )

    generated, ok = await content_planner.generate_content_plan("context", days=14)

    assert ok is True
    assert len(generated.items) == 1
    assert generated.items[0].title == "Valid item"


async def test_generate_content_plan_skips_items_missing_title_or_description(monkeypatch):
    monkeypatch.setattr(content_planner.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        content_planner,
        "_client",
        _fake_client_returning(
            [
                # content_type/platform present, but title/description missing —
                # previously raised an uncaught KeyError and crashed the whole plan.
                {"content_type": "post", "platform": "linkedin", "days_from_now": 1},
                {
                    "title": "Valid item",
                    "description": "d",
                    "draft_copy": "dc",
                    "content_type": "post",
                    "platform": "linkedin",
                    "days_from_now": 1,
                },
            ]
        ),
    )

    generated, ok = await content_planner.generate_content_plan("context", days=14)

    assert ok is True
    assert len(generated.items) == 1
    assert generated.items[0].title == "Valid item"


async def test_generate_content_plan_skips_items_with_non_numeric_days_from_now(monkeypatch):
    monkeypatch.setattr(content_planner.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        content_planner,
        "_client",
        _fake_client_returning(
            [
                {
                    "title": "Bad days_from_now",
                    "description": "d",
                    "content_type": "post",
                    "platform": "linkedin",
                    "days_from_now": "soon",
                },
                {
                    "title": "Valid item",
                    "description": "d",
                    "draft_copy": "dc",
                    "content_type": "post",
                    "platform": "linkedin",
                    "days_from_now": 1,
                },
            ]
        ),
    )

    generated, ok = await content_planner.generate_content_plan("context", days=14)

    assert ok is True
    assert len(generated.items) == 1
    assert generated.items[0].title == "Valid item"


async def test_generate_content_plan_empty_related_trend_becomes_none(monkeypatch):
    monkeypatch.setattr(content_planner.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        content_planner,
        "_client",
        _fake_client_returning(
            [
                {
                    "title": "No trend tie-in",
                    "description": "d",
                    "draft_copy": "dc",
                    "content_type": "post",
                    "platform": "blog",
                    "days_from_now": 0,
                    "related_trend_title": "",
                },
            ]
        ),
    )

    generated, ok = await content_planner.generate_content_plan("context", days=14)

    assert ok is True
    assert generated.items[0].related_trend_title is None


def test_seasonal_candidates_finds_fixed_date_events_in_window():
    start = date(2026, 12, 20)
    candidates = content_planner.seasonal_candidates(start, days=14)

    assert any("Christmas" in c and "2026-12-25" in c for c in candidates)
    assert any("New Year's Eve" in c and "2026-12-31" in c for c in candidates)
    assert any("New Year's Day" in c and "2027-01-01" in c for c in candidates)


def test_seasonal_candidates_empty_when_no_events_in_window():
    # Mar 15 - Mar 25 has no fixed-date events in the lookup table.
    start = date(2026, 3, 15)
    candidates = content_planner.seasonal_candidates(start, days=10)

    assert candidates == []


async def test_generate_content_plan_parses_audience_interest_and_seasonal_event(monkeypatch):
    monkeypatch.setattr(content_planner.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        content_planner,
        "_client",
        _fake_client_returning(
            [
                {
                    "title": "Christmas gift guide",
                    "description": "d",
                    "draft_copy": "dc",
                    "content_type": "post",
                    "platform": "instagram",
                    "days_from_now": 0,
                    "audience_interest": "parents shopping for young kids",
                    "seasonal_event": "Christmas (2026-12-25)",
                },
            ]
        ),
    )

    generated, ok = await content_planner.generate_content_plan("context", days=14)

    assert ok is True
    item = generated.items[0]
    assert item.audience_interest == "parents shopping for young kids"
    assert item.seasonal_event == "Christmas (2026-12-25)"


async def test_generate_content_plan_empty_audience_interest_and_seasonal_event_become_none(monkeypatch):
    monkeypatch.setattr(content_planner.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        content_planner,
        "_client",
        _fake_client_returning(
            [
                {
                    "title": "Evergreen post",
                    "description": "d",
                    "draft_copy": "dc",
                    "content_type": "post",
                    "platform": "instagram",
                    "days_from_now": 0,
                    "audience_interest": "",
                    "seasonal_event": "",
                },
            ]
        ),
    )

    generated, ok = await content_planner.generate_content_plan("context", days=14)

    assert ok is True
    item = generated.items[0]
    assert item.audience_interest is None
    assert item.seasonal_event is None


async def test_generate_content_plan_skips_items_missing_draft_copy(monkeypatch):
    monkeypatch.setattr(content_planner.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        content_planner,
        "_client",
        _fake_client_returning(
            [
                # draft_copy omitted — required now that the whole point is
                # a finished, publishable post, not a brief.
                {
                    "title": "No draft",
                    "description": "d",
                    "content_type": "post",
                    "platform": "linkedin",
                    "days_from_now": 1,
                },
                {
                    "title": "Valid item",
                    "description": "d",
                    "draft_copy": "Ready-to-publish text.",
                    "content_type": "post",
                    "platform": "linkedin",
                    "days_from_now": 1,
                },
            ]
        ),
    )

    generated, ok = await content_planner.generate_content_plan("context", days=14)

    assert ok is True
    assert len(generated.items) == 1
    assert generated.items[0].title == "Valid item"


async def test_regenerate_draft_copy_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(content_planner.settings, "ANTHROPIC_API_KEY", "")

    draft, ok = await content_planner.regenerate_draft_copy("context", "T", "d", "post", "instagram")

    assert ok is False
    assert draft is None


async def test_regenerate_draft_copy_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(content_planner.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(content_planner, "_client", lambda: _FailingClient())

    draft, ok = await content_planner.regenerate_draft_copy("context", "T", "d", "post", "instagram")

    assert ok is False
    assert draft is None


async def test_regenerate_draft_copy_returns_new_copy_on_success(monkeypatch):
    monkeypatch.setattr(content_planner.settings, "ANTHROPIC_API_KEY", "test-key")
    tool_use = SimpleNamespace(
        type="tool_use", input={"draft_copy": "A brand new caption ready to post."}
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(content=[tool_use])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(content_planner, "_client", lambda: _FakeClient())

    draft, ok = await content_planner.regenerate_draft_copy(
        "context", "Title", "brief", "post", "instagram"
    )

    assert ok is True
    assert draft == "A brand new caption ready to post."


async def test_generate_content_plan_injects_seasonal_context_into_prompt(monkeypatch):
    monkeypatch.setattr(content_planner.settings, "ANTHROPIC_API_KEY", "test-key")

    captured = {}
    tool_use = SimpleNamespace(type="tool_use", input={"items": []})

    class _CapturingMessages:
        async def create(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            return SimpleNamespace(content=[tool_use])

    class _CapturingClient:
        messages = _CapturingMessages()

    monkeypatch.setattr(content_planner, "_client", lambda: _CapturingClient())

    # A 14-day window from today may or may not contain a fixed-date event —
    # force it deterministically by monkeypatching the candidate lookup.
    monkeypatch.setattr(
        content_planner, "seasonal_candidates", lambda start, days: ["Halloween (2026-10-31)"]
    )

    await content_planner.generate_content_plan("context", days=14)

    prompt = captured["messages"][0]["content"]
    assert "Halloween (2026-10-31)" in prompt
    assert "Seasonal/awareness dates" in prompt
