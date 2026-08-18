"""Tests for the chat agent's multi-turn tool-use loop.

Unlike every other agent's single forced-tool call, this loop needs its
own dedicated coverage of the iteration/termination logic — the one
genuinely new pattern in this codebase — independent of live Claude
credit. Most tests here also don't need a real DB (pass `session=None`);
the exception is `_describe_action`'s own coverage below, since it now
does a real lookup to avoid putting a raw id in front of the user.
"""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import respx

from app.agents.chat import agent
from app.db.models import Company, ContentItem, ContentPlan, Document
from app.security.auth import CurrentUser

_USER = CurrentUser(id="test-user-id", email="test@example.com")


async def test_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr(agent.settings, "ANTHROPIC_API_KEY", "")

    text, tools_used, ok, proposed_action, cards = await agent.run_chat_turn(
        [{"role": "user", "content": "hi"}], None, None, _USER
    )

    assert ok is False
    assert tools_used == []
    assert proposed_action is None
    assert cards == []
    assert "isn't available" in text


async def test_chat_call_uses_prompt_caching_on_system_and_tools(monkeypatch):
    """The fixed system prompt + tool schemas (identical on every call, for
    every company) must carry a cache_control breakpoint — see the
    comment above _SYSTEM_PROMPT_BLOCKS/_CACHED_SCHEMAS in agent.py for
    why this is the single highest-leverage cost optimization available."""
    monkeypatch.setattr(agent.settings, "ANTHROPIC_API_KEY", "test-key")

    text_block = SimpleNamespace(type="text", text="Hello!")
    captured_kwargs = {}

    class _FakeMessages:
        async def create(self, **kwargs):
            captured_kwargs.update(kwargs)
            return SimpleNamespace(stop_reason="end_turn", content=[text_block])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(agent, "_client", lambda: _FakeClient())

    await agent.run_chat_turn([{"role": "user", "content": "hello"}], None, None, _USER)

    system = captured_kwargs["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert system[0]["text"] == agent._SYSTEM_PROMPT

    tools = captured_kwargs["tools"]
    assert tools[-1]["cache_control"] == {"type": "ephemeral"}
    # Every tool schema is still present, just the last one gains a key —
    # nothing was dropped or reordered by adding the breakpoint.
    assert len(tools) == len(agent._ALL_SCHEMAS)
    assert [t["name"] for t in tools] == [t["name"] for t in agent._ALL_SCHEMAS]


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
        [{"role": "user", "content": "hello"}], None, None, _USER
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
        [{"role": "user", "content": "what's trending?"}], None, None, _USER
    )

    assert ok is True
    assert text == "Here's what's trending: X, Y, Z."
    assert tools_used == ["list_trending_topics"]
    assert proposed_action is None
    assert cards == [{"type": "trend", "title": "X"}]
    assert call_count == 2


def test_merge_cards_drops_a_repeat_of_the_same_type_and_id():
    existing = [{"type": "content_item", "id": "abc", "title": "old"}]
    new = [
        {"type": "content_item", "id": "abc", "title": "same item again"},
        {"type": "content_item", "id": "xyz", "title": "a different item"},
    ]

    merged = agent._merge_cards(existing, new)

    assert merged == [
        {"type": "content_item", "id": "abc", "title": "old"},
        {"type": "content_item", "id": "xyz", "title": "a different item"},
    ]


async def test_two_tool_calls_in_one_turn_surfacing_the_same_item_produce_one_card(monkeypatch):
    # Reproduces the real bug: Claude calling find_content_items twice in
    # the same turn (e.g. once to check, once right before proposing a
    # write action) and both calls surfacing the same item — previously
    # this put two cards with the same id as siblings in one message,
    # which is a real React duplicate-key error on the frontend, not just
    # a cosmetic one.
    monkeypatch.setattr(agent.settings, "ANTHROPIC_API_KEY", "test-key")

    same_card = {"type": "content_item", "id": "item-1", "title": "Community Q&A"}
    tool_use_1 = SimpleNamespace(
        type="tool_use", id="tool-1", name="find_content_items", input={}
    )
    tool_use_2 = SimpleNamespace(
        type="tool_use", id="tool-2", name="find_content_items", input={"query": "again"}
    )
    final_text_block = SimpleNamespace(type="text", text="Found it.")

    responses = [
        SimpleNamespace(stop_reason="tool_use", content=[tool_use_1, tool_use_2]),
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

    async def _fake_find_content_items(session, **kwargs):
        return "Found 1 matching item(s): Community Q&A (id: item-1)", [same_card]

    monkeypatch.setitem(agent.TOOL_IMPLEMENTATIONS, "find_content_items", _fake_find_content_items)

    text, tools_used, ok, proposed_action, cards = await agent.run_chat_turn(
        [{"role": "user", "content": "find that post, then find it again"}], None, None, _USER
    )

    assert ok is True
    assert tools_used == ["find_content_items", "find_content_items"]
    # Both calls returned the same card — only one should survive.
    assert cards == [same_card]


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
        [{"role": "user", "content": "loop forever"}], None, None, _USER
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
        [{"role": "user", "content": "hi"}], None, None, _USER
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
        [{"role": "user", "content": "approve item abc-123"}], None, None, _USER
    )

    assert ok is True
    assert executed is False
    assert tools_used == []
    assert call_count == 1
    assert proposed_action == {
        "tool_name": "approve_content_item",
        "tool_input": {"content_item_id": "abc-123"},
        "description": "Approve that item",
        "confirmation_phrase": None,
    }
    assert text == "Approve that item"
    # "abc-123" isn't a real UUID, so there's no item to preview — the
    # proposal still stands, just without a flashcard attached.
    assert cards == []


async def _seed_item_with_plan(test_session_factory) -> tuple[uuid.UUID, uuid.UUID]:
    from app.db.models import Company

    item_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="complete", is_manual=True))
        session.add(
            ContentItem(
                id=item_id,
                content_plan_id=plan_id,
                title="A real item",
                description="",
                content_type="post",
                platform="linkedin",
                suggested_date=date.today(),
                approval_status="pending",
            )
        )
        await session.commit()
    return item_id, company_id


async def _run_write_tool_proposal(
    monkeypatch, tool_name: str, item_id: uuid.UUID, test_session_factory
) -> list[dict]:
    monkeypatch.setattr(agent.settings, "ANTHROPIC_API_KEY", "test-key")
    write_tool_block = SimpleNamespace(
        type="tool_use", id="tool-1", name=tool_name, input={"content_item_id": str(item_id)}
    )

    class _FakeMessages:
        async def create(self, **kwargs):
            return SimpleNamespace(stop_reason="tool_use", content=[write_tool_block])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(agent, "_client", lambda: _FakeClient())

    async with test_session_factory() as session:
        _, _, _, _, cards = await agent.run_chat_turn(
            [{"role": "user", "content": "do the thing"}], None, session, _USER
        )
    return cards


async def test_publish_proposal_card_has_action_context(monkeypatch, test_session_factory):
    """Publishing is literally what's being proposed — the card must carry
    publish/schedule controls, since that's exactly what the user's own
    request implied."""
    item_id, _ = await _seed_item_with_plan(test_session_factory)
    cards = await _run_write_tool_proposal(
        monkeypatch, "publish_content_item", item_id, test_session_factory
    )
    assert len(cards) == 1
    assert cards[0]["card_context"] == "action"


async def test_schedule_proposal_card_has_action_context(monkeypatch, test_session_factory):
    item_id, _ = await _seed_item_with_plan(test_session_factory)
    cards = await _run_write_tool_proposal(
        monkeypatch, "schedule_content_item", item_id, test_session_factory
    )
    assert len(cards) == 1
    assert cards[0]["card_context"] == "action"


async def test_approve_proposal_card_has_preview_context_not_action(monkeypatch, test_session_factory):
    """Approving isn't posting — this card is informational, so it must
    NOT carry publish/schedule controls just because it happens to be
    attached to a write-tool proposal."""
    item_id, _ = await _seed_item_with_plan(test_session_factory)
    cards = await _run_write_tool_proposal(
        monkeypatch, "approve_content_item", item_id, test_session_factory
    )
    assert len(cards) == 1
    assert cards[0]["card_context"] == "preview"


async def test_describe_action_uses_item_title_not_raw_id(test_session_factory, db_session):
    item_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        from app.db.models import Company

        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        session.add(ContentPlan(id=plan_id, company_id=company_id, status="complete", is_manual=True))
        session.add(
            ContentItem(
                id=item_id,
                content_plan_id=plan_id,
                title="Community Q&A tomorrow — drop your questions",
                description="",
                content_type="post",
                platform="youtube",
                suggested_date=date.today(),
                approval_status="pending",
            )
        )
        await session.commit()

    description = await agent._describe_action(
        "publish_content_item", {"content_item_id": str(item_id)}, db_session
    )

    assert description == 'Publish "Community Q&A tomorrow — drop your questions" now'
    assert str(item_id) not in description


async def test_describe_action_falls_back_to_generic_phrase_for_unknown_item(db_session):
    description = await agent._describe_action(
        "approve_content_item", {"content_item_id": str(uuid.uuid4())}, db_session
    )
    assert description == "Approve that item"


async def test_describe_action_uses_company_name_not_raw_id(test_session_factory, db_session):
    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        from app.db.models import Company

        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        await session.commit()

    description = await agent._describe_action(
        "create_content_plan", {"company_id": str(company_id), "days": 7}, db_session
    )

    assert description == "Create a new content plan for Acme (7 days)"
    assert str(company_id) not in description


# --- _auto_ingest_document_attachments ------------------------------------
#
# Real bug this fixes: attaching a file in chat only ever uploaded it to
# storage and dropped a link in the message text — nothing made it
# searchable, so "use this doc to write this week's posts" silently had
# no real document behind it (reported live, see the screenshot this was
# built from).

from sqlalchemy import select as _select  # noqa: E402  (grouped near its one use below)

_ATTACHMENT_URL = "https://test-project.supabase.co/storage/v1/object/public/chat-attachments/report.txt"


async def _fake_embed(texts):
    return [[0.1] * 1024 for _ in texts]


async def _seed_company_for_ingest(test_session_factory) -> uuid.UUID:
    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url=f"https://example.com/{company_id}", status="complete"))
        await session.commit()
    return company_id


async def test_auto_ingest_returns_empty_without_a_company(db_session):
    result = await agent._auto_ingest_document_attachments(
        db_session, None, "here's the doc [report.txt](https://example.com/report.txt)"
    )

    assert result == []


@respx.mock
async def test_auto_ingest_extracts_and_persists_a_document_attachment(
    monkeypatch, test_session_factory
):
    from app.agents.knowledge_base import ingestion as ingestion_module

    monkeypatch.setattr(ingestion_module, "embed_documents", _fake_embed)
    monkeypatch.setattr(agent, "validate_public_url", lambda url: None)
    respx.get(_ATTACHMENT_URL).mock(
        return_value=httpx.Response(200, content=b"Q3 revenue grew 40% year over year.")
    )
    company_id = await _seed_company_for_ingest(test_session_factory)

    async with test_session_factory() as session:
        result = await agent._auto_ingest_document_attachments(
            session,
            company_id,
            f"use this docs to write the content [Research Report.txt]({_ATTACHMENT_URL})",
        )
        await session.commit()

    assert result == ["Research Report.txt"]
    async with test_session_factory() as session:
        rows = (
            await session.execute(_select(Document).where(Document.company_id == company_id))
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].source_type == "chat_attachment"
    assert "Q3 revenue grew 40%" in rows[0].content


@respx.mock
async def test_auto_ingest_ignores_image_attachments(monkeypatch, test_session_factory):
    """`![...]` is an image (see chat-attachments.ts) — must not be
    treated as a document to extract."""
    from app.agents.knowledge_base import ingestion as ingestion_module

    monkeypatch.setattr(ingestion_module, "embed_documents", _fake_embed)
    monkeypatch.setattr(agent, "validate_public_url", lambda url: None)
    company_id = await _seed_company_for_ingest(test_session_factory)

    async with test_session_factory() as session:
        result = await agent._auto_ingest_document_attachments(
            session, company_id, "![photo.png](https://example.com/photo.png)"
        )

    assert result == []


async def test_auto_ingest_ignores_non_document_extensions(test_session_factory):
    company_id = await _seed_company_for_ingest(test_session_factory)

    async with test_session_factory() as session:
        result = await agent._auto_ingest_document_attachments(
            session, company_id, "[video.mp4](https://example.com/video.mp4)"
        )

    assert result == []


@respx.mock
async def test_auto_ingest_never_raises_on_a_fetch_failure(monkeypatch, test_session_factory):
    monkeypatch.setattr(agent, "validate_public_url", lambda url: None)
    respx.get(_ATTACHMENT_URL).mock(return_value=httpx.Response(404))
    company_id = await _seed_company_for_ingest(test_session_factory)

    async with test_session_factory() as session:
        result = await agent._auto_ingest_document_attachments(
            session, company_id, f"[report.txt]({_ATTACHMENT_URL})"
        )

    assert result == []


async def test_auto_ingest_refuses_an_unsafe_url(test_session_factory):
    """The URL in a chat message is attacker-controllable — must go
    through the same SSRF guard used before fetching any other
    user-supplied URL, never fetched unconditionally."""
    company_id = await _seed_company_for_ingest(test_session_factory)

    async with test_session_factory() as session:
        result = await agent._auto_ingest_document_attachments(
            session, company_id, "[report.txt](http://169.254.169.254/latest/meta-data/report.txt)"
        )

    assert result == []


async def test_run_chat_turn_annotates_the_message_when_a_doc_was_ingested(
    monkeypatch, test_session_factory
):
    """The model must actually be told ingestion happened within the same
    turn — otherwise "use this doc" on the very message that attached it
    has nothing real to search yet from the model's point of view."""
    monkeypatch.setattr(agent.settings, "ANTHROPIC_API_KEY", "test-key")
    company_id = await _seed_company_for_ingest(test_session_factory)

    fake_ingest = AsyncMock(return_value=["Research Report.txt"])
    monkeypatch.setattr(agent, "_auto_ingest_document_attachments", fake_ingest)

    captured_kwargs = {}
    text_block = SimpleNamespace(type="text", text="Got it.")

    class _FakeMessages:
        async def create(self, **kwargs):
            captured_kwargs.update(kwargs)
            return SimpleNamespace(stop_reason="end_turn", content=[text_block])

    class _FakeClient:
        messages = _FakeMessages()

    monkeypatch.setattr(agent, "_client", lambda: _FakeClient())

    async with test_session_factory() as session:
        await agent.run_chat_turn(
            [{"role": "user", "content": "use this doc [Research Report.txt](https://x/report.txt)"}],
            company_id,
            session,
            _USER,
        )

    fake_ingest.assert_awaited_once()
    sent_messages = captured_kwargs["messages"]
    assert "automatically added to the knowledge base" in sent_messages[-1]["content"]
    assert "Research Report.txt" in sent_messages[-1]["content"]
