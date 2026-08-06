"""Tests for the chat agent's multi-turn tool-use loop.

Unlike every other agent's single forced-tool call, this loop needs its
own dedicated coverage of the iteration/termination logic — the one
genuinely new pattern in this codebase — independent of a real DB or
live Claude credit.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.chat import agent


async def test_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(agent.settings, "ANTHROPIC_API_KEY", "")

    text, tools_used, ok, proposed_action, cards = await agent.run_chat_turn(
        [{"role": "user", "content": "hi"}], None, None
    )

    assert ok is False
    assert tools_used == []
    assert proposed_action is None
    assert cards == []
    assert "isn't available" in text


async def test_answers_directly_without_a_tool_call(monkeypatch):
    monkeypatch.setattr(agent.settings, "ANTHROPIC_API_KEY", "test-key")

    text_block = SimpleNamespace(type="text", text="Hello! How can I help?")

    call_count = 0

    class _FakeMessages:
        async def create(self, **kwargs):
            nonlocal call_count
            call_count += 1
            return SimpleNamespace(stop_reason="end_turn", content=[text_block])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(agent, "_client", lambda: _FakeClient())

    text, tools_used, ok, proposed_action, cards = await agent.run_chat_turn(
        [{"role": "user", "content": "hello"}], None, None
    )

    assert ok is True
    assert text == "Hello! How can I help?"
    assert tools_used == []
    assert proposed_action is None
    assert cards == []
    assert call_count == 1


async def test_executes_a_tool_call_then_returns_final_answer(monkeypatch):
    monkeypatch.setattr(agent.settings, "ANTHROPIC_API_KEY", "test-key")

    tool_use_block = SimpleNamespace(
        type="tool_use", id="tool-1", name="list_trending_topics", input={"limit": 3}
    )
    final_text_block = SimpleNamespace(type="text", text="Here's what's trending: X, Y, Z.")

    responses = [
        SimpleNamespace(stop_reason="tool_use", content=[tool_use_block]),
        SimpleNamespace(stop_reason="end_turn", content=[final_text_block]),
    ]
    call_count = 0

    class _FakeMessages:
        async def create(self, **kwargs):
            nonlocal call_count
            response = responses[call_count]
            call_count += 1
            return response

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(agent, "_client", lambda: _FakeClient())

    async def _fake_list_trending_topics(session, **kwargs):
        return "Trending topics:\n- X\n- Y\n- Z", [{"type": "trend", "title": "X"}]

    monkeypatch.setitem(
        agent.TOOL_IMPLEMENTATIONS, "list_trending_topics", _fake_list_trending_topics
    )

    text, tools_used, ok, proposed_action, cards = await agent.run_chat_turn(
        [{"role": "user", "content": "what's trending?"}], None, None
    )

    assert ok is True
    assert text == "Here's what's trending: X, Y, Z."
    assert tools_used == ["list_trending_topics"]
    assert proposed_action is None
    assert cards == [{"type": "trend", "title": "X"}]
    assert call_count == 2


async def test_iteration_cap_forces_a_final_answer_with_tools_disabled(monkeypatch):
    monkeypatch.setattr(agent.settings, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(agent.settings, "CHAT_MAX_ITERATIONS", 2)

    tool_use_block = SimpleNamespace(
        type="tool_use", id="tool-1", name="list_trending_topics", input={}
    )
    forced_text_block = SimpleNamespace(type="text", text="Here's my best answer so far.")

    call_kwargs: list[dict] = []

    class _FakeMessages:
        async def create(self, **kwargs):
            call_kwargs.append(kwargs)
            if kwargs["tool_choice"] == {"type": "none"}:
                return SimpleNamespace(stop_reason="end_turn", content=[forced_text_block])
            return SimpleNamespace(stop_reason="tool_use", content=[tool_use_block])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(agent, "_client", lambda: _FakeClient())

    async def _fake_list_trending_topics(session, **kwargs):
        return "some trends"

    monkeypatch.setitem(
        agent.TOOL_IMPLEMENTATIONS, "list_trending_topics", _fake_list_trending_topics
    )

    text, tools_used, ok, proposed_action, cards = await agent.run_chat_turn(
        [{"role": "user", "content": "loop forever"}], None, None
    )

    assert ok is True
    assert text == "Here's my best answer so far."
    assert proposed_action is None
    assert cards == []
    # 2 tool-loop iterations (CHAT_MAX_ITERATIONS) + 1 forced final call
    assert len(call_kwargs) == 3
    assert call_kwargs[-1]["tool_choice"] == {"type": "none"}


async def test_falls_back_on_api_failure(monkeypatch):
    monkeypatch.setattr(agent.settings, "ANTHROPIC_API_KEY", "test-key")

    class _FailingMessages:
        async def create(self, **kwargs):
            raise RuntimeError("Anthropic API error")

    class _FailingClient:
        messages = _FailingMessages()

    monkeypatch.setattr(agent, "_client", lambda: _FailingClient())

    text, tools_used, ok, proposed_action, cards = await agent.run_chat_turn(
        [{"role": "user", "content": "hi"}], None, None
    )

    assert ok is False
    assert proposed_action is None
    assert cards == []
    assert "went wrong" in text


async def test_a_write_tool_call_ends_the_turn_as_a_proposal_not_an_execution(monkeypatch):
    monkeypatch.setattr(agent.settings, "ANTHROPIC_API_KEY", "test-key")

    write_tool_block = SimpleNamespace(
        type="tool_use",
        id="tool-1",
        name="approve_content_item",
        input={"content_item_id": "abc-123"},
    )

    call_count = 0
    executed = False

    class _FakeMessages:
        async def create(self, **kwargs):
            nonlocal call_count
            call_count += 1
            return SimpleNamespace(stop_reason="tool_use", content=[write_tool_block])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(agent, "_client", lambda: _FakeClient())

    async def _fake_approve(session, **kwargs):
        nonlocal executed
        executed = True
        return "should never run"

    monkeypatch.setitem(agent.WRITE_TOOL_IMPLEMENTATIONS, "approve_content_item", _fake_approve)

    text, tools_used, ok, proposed_action, cards = await agent.run_chat_turn(
        [{"role": "user", "content": "approve item abc-123"}], None, None
    )

    assert ok is True
    assert executed is False
    assert tools_used == []
    assert call_count == 1
    assert proposed_action == {
        "tool_name": "approve_content_item",
        "tool_input": {"content_item_id": "abc-123"},
        "description": "Approve content item abc-123",
    }
    assert text == "Approve content item abc-123"
    # "abc-123" isn't a real UUID, so there's no item to preview — the
    # proposal still stands, just without a flashcard attached.
    assert cards == []
