"""API tests for the intelligent chat routes."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.agents.chat import agent as agent_module
from app.api.v1.endpoints import chat as chat_module
from app.db.models import ChatMessage, Company, ContentItem, ContentPlan
from app.db.session import get_session
from app.security.auth import CurrentUser, get_current_user


@pytest_asyncio.fixture
async def seeded_company(test_session_factory):
    """A real Company row. Conversations and proposed actions now resolve
    to a real company for their ownership check, so these can't use
    made-up ids any more."""
    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        await session.commit()
    return company_id


@pytest_asyncio.fixture
async def seeded_content_item(test_session_factory, seeded_company):
    """A real ContentItem reachable from a real Company via its plan —
    what `confirm-action` now re-checks ownership against before running a
    proposed write tool."""
    item_id = uuid.uuid4()
    plan_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(ContentPlan(id=plan_id, company_id=seeded_company, status="complete"))
        session.add(
            ContentItem(
                id=item_id,
                content_plan_id=plan_id,
                title="Test post",
                description="A test post.",
                content_type="post",
                platform="instagram",
                suggested_date=date(2026, 8, 5),
            )
        )
        await session.commit()
    return item_id


@pytest_asyncio.fixture
async def client(monkeypatch, test_session_factory):
    async def _fake_run_chat_turn(history, company_id, session, user):
        return ("Fake assistant reply.", ["list_trending_topics"], True, None, [])

    async def _fake_run_chat_turn_stream(history, company_id, session, user):
        for word in ["Fake ", "streamed ", "reply."]:
            yield ("token", word)
        yield (
            "done",
            {"tools_used": ["list_trending_topics"], "proposed_action": None, "cards": [], "ok": True},
        )

    async def _fake_generate_conversation_title(user_message):
        if user_message == "trigger-title-failure":
            return None
        return f"Title for: {user_message}"

    monkeypatch.setattr(chat_module, "run_chat_turn", _fake_run_chat_turn)
    monkeypatch.setattr(chat_module, "run_chat_turn_stream", _fake_run_chat_turn_stream)
    monkeypatch.setattr(
        chat_module, "generate_conversation_title", _fake_generate_conversation_title
    )

    app = FastAPI()
    app.include_router(chat_module.router)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="test-user-id", email="test@example.com"
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_create_conversation(client):
    response = await client.post("/conversations", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["company_id"] is None
    assert body["title"] is None


async def test_create_conversation_scoped_to_company(client, seeded_company):
    response = await client.post(
        "/conversations", json={"company_id": str(seeded_company)}
    )
    assert response.status_code == 200
    assert response.json()["company_id"] == str(seeded_company)


async def test_create_conversation_404s_for_a_company_that_does_not_exist(client):
    """Scoping a conversation to a company is an access decision now, not
    just a label — an unknown (or someone else's) company id is a 404."""
    response = await client.post(
        "/conversations", json={"company_id": str(uuid.uuid4())}
    )
    assert response.status_code == 404


async def test_list_conversations(client):
    await client.post("/conversations", json={})
    await client.post("/conversations", json={})

    response = await client.get("/conversations")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


async def test_get_conversation_includes_messages(client):
    created = (await client.post("/conversations", json={})).json()
    await client.post(f"/conversations/{created['id']}/messages", json={"content": "hi there"})

    response = await client.get(f"/conversations/{created['id']}")
    body = response.json()
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][0]["content"] == "hi there"
    assert body["messages"][1]["role"] == "assistant"
    assert body["messages"][1]["content"] == "Fake assistant reply."


async def test_get_conversation_404(client):
    response = await client.get(f"/conversations/{uuid.uuid4()}")
    assert response.status_code == 404


async def test_delete_conversation(client):
    created = (await client.post("/conversations", json={})).json()

    response = await client.delete(f"/conversations/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]

    response = await client.get(f"/conversations/{created['id']}")
    assert response.status_code == 404


async def test_send_message_sets_title_from_generated_intent(client):
    created = (await client.post("/conversations", json={})).json()

    response = await client.post(
        f"/conversations/{created['id']}/messages", json={"content": "What's trending?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "assistant"
    assert body["content"] == "Fake assistant reply."
    assert body["tool_calls_summary"] == ["list_trending_topics"]
    assert body["ok"] is True

    conversation = (await client.get(f"/conversations/{created['id']}")).json()
    assert conversation["title"] == "Title for: What's trending?"


async def test_send_message_title_falls_back_to_raw_message_if_generation_fails(client):
    created = (await client.post("/conversations", json={})).json()

    await client.post(
        f"/conversations/{created['id']}/messages",
        json={"content": "trigger-title-failure"},
    )

    conversation = (await client.get(f"/conversations/{created['id']}")).json()
    assert conversation["title"] == "trigger-title-failure"


async def test_send_message_does_not_rename_an_already_titled_conversation(client):
    created = (await client.post("/conversations", json={})).json()
    await client.post(f"/conversations/{created['id']}/messages", json={"content": "first"})

    await client.post(f"/conversations/{created['id']}/messages", json={"content": "second"})

    conversation = (await client.get(f"/conversations/{created['id']}")).json()
    assert conversation["title"] == "Title for: first"


async def test_send_message_stream_persists_the_assistant_reply(client):
    created = (await client.post("/conversations", json={})).json()

    response = await client.post(
        f"/conversations/{created['id']}/messages/stream",
        json={"content": "What's trending?"},
    )
    assert response.status_code == 200
    assert "Fake streamed reply." in response.text

    conversation = (await client.get(f"/conversations/{created['id']}")).json()
    assert len(conversation["messages"]) == 2
    assert conversation["messages"][1]["content"] == "Fake streamed reply."


async def test_send_message_stream_sets_title_from_generated_intent(client):
    """Regression test for a real bug: `_get_conversation_or_404` loads
    `conversation` using the request's injected `session`, but
    `_event_generator` runs *after* `send_message_stream` returns —  by
    which point FastAPI has already torn down that `Depends(get_session)`
    dependency, detaching every object it had loaded (confirmed live via
    `sqlalchemy.orm.object_session(conversation) is None` at that point).
    A detached object's mutations are never flushed, so `conversation.title
    = ...` was silently lost on every single streamed reply — the
    conversation sidebar's `title is not None` filter meant this hid every
    conversation ever created through the (exclusively-used-by-the-
    frontend) streaming endpoint. Fixed by re-adding `conversation` to the
    session before mutating it."""
    created = (await client.post("/conversations", json={})).json()

    await client.post(
        f"/conversations/{created['id']}/messages/stream",
        json={"content": "What's trending?"},
    )

    conversation = (await client.get(f"/conversations/{created['id']}")).json()
    assert conversation["title"] == "Title for: What's trending?"


async def test_send_message_stream_title_falls_back_to_raw_message_if_generation_fails(client):
    created = (await client.post("/conversations", json={})).json()

    await client.post(
        f"/conversations/{created['id']}/messages/stream",
        json={"content": "trigger-title-failure"},
    )

    conversation = (await client.get(f"/conversations/{created['id']}")).json()
    assert conversation["title"] == "trigger-title-failure"


async def test_send_message_stream_does_not_rename_an_already_titled_conversation(client):
    created = (await client.post("/conversations", json={})).json()
    await client.post(
        f"/conversations/{created['id']}/messages/stream", json={"content": "first"}
    )

    await client.post(
        f"/conversations/{created['id']}/messages/stream", json={"content": "second"}
    )

    conversation = (await client.get(f"/conversations/{created['id']}")).json()
    assert conversation["title"] == "Title for: first"


async def test_send_message_404_for_unknown_conversation(client):
    response = await client.post(
        f"/conversations/{uuid.uuid4()}/messages", json={"content": "hi"}
    )
    assert response.status_code == 404


async def test_send_message_requires_auth(test_session_factory):
    app = FastAPI()
    app.include_router(chat_module.router)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        response = await async_client.post("/conversations", json={})
    assert response.status_code == 401


async def test_send_message_real_graceful_degradation_without_api_key(
    monkeypatch, test_session_factory
):
    """Uses the REAL run_chat_turn (not the fixture's fake) with a real
    empty ANTHROPIC_API_KEY — exercises the actual graceful-degradation
    code path end-to-end through the endpoint, not a mock of it."""
    monkeypatch.setattr(agent_module.settings, "ANTHROPIC_API_KEY", "")

    app = FastAPI()
    app.include_router(chat_module.router)

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id="test-user-id", email="test@example.com"
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        created = (await async_client.post("/conversations", json={})).json()
        response = await async_client.post(
            f"/conversations/{created['id']}/messages", json={"content": "hi"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "isn't available" in body["content"]


async def test_confirm_action_executes_the_proposed_tool(
    client, monkeypatch, seeded_content_item
):
    proposed_action = {
        "tool_name": "approve_content_item",
        "tool_input": {"content_item_id": str(seeded_content_item)},
        "description": "Approve the content item",
    }

    async def _fake_with_proposal(history, company_id, session, user):
        return ("I'll approve that.", [], True, proposed_action, [])

    monkeypatch.setattr(chat_module, "run_chat_turn", _fake_with_proposal)

    executed_with: dict = {}

    async def _fake_approve(session, **kwargs):
        executed_with.update(kwargs)
        return "Approved content item 'Test post'."

    monkeypatch.setitem(chat_module.WRITE_TOOL_IMPLEMENTATIONS, "approve_content_item", _fake_approve)

    created = (await client.post("/conversations", json={})).json()
    sent = (
        await client.post(
            f"/conversations/{created['id']}/messages", json={"content": "approve it"}
        )
    ).json()
    assert sent["proposed_action"] == proposed_action
    assert sent["action_status"] == "pending"

    response = await client.post(
        f"/conversations/{created['id']}/messages/{sent['id']}/confirm-action"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action_status"] == "confirmed"
    assert executed_with == {"content_item_id": str(seeded_content_item)}

    conversation = (await client.get(f"/conversations/{created['id']}")).json()
    assert conversation["messages"][-1]["content"] == "Approved content item 'Test post'."


async def test_confirm_action_requires_the_exact_typed_phrase_when_the_proposal_needs_one(
    client, monkeypatch, seeded_content_item
):
    """delete_content_item_post-style actions carry a confirmation_phrase
    on the proposal — the endpoint must reject confirming without it (or
    with the wrong text) regardless of what the frontend's own button
    state does, since that's just UX, not the actual safety boundary."""
    proposed_action = {
        "tool_name": "approve_content_item",
        "tool_input": {"content_item_id": str(seeded_content_item)},
        "description": "Permanently delete that item",
        "confirmation_phrase": "DELETE",
    }

    async def _fake_with_proposal(history, company_id, session, user):
        return ("I'll delete that.", [], True, proposed_action, [])

    monkeypatch.setattr(chat_module, "run_chat_turn", _fake_with_proposal)

    executed = False

    async def _fake_approve(session, **kwargs):
        nonlocal executed
        executed = True
        return "done"

    monkeypatch.setitem(chat_module.WRITE_TOOL_IMPLEMENTATIONS, "approve_content_item", _fake_approve)

    created = (await client.post("/conversations", json={})).json()
    sent = (
        await client.post(
            f"/conversations/{created['id']}/messages", json={"content": "delete it"}
        )
    ).json()

    # No body at all.
    response = await client.post(
        f"/conversations/{created['id']}/messages/{sent['id']}/confirm-action"
    )
    assert response.status_code == 400
    assert executed is False

    # Wrong text.
    response = await client.post(
        f"/conversations/{created['id']}/messages/{sent['id']}/confirm-action",
        json={"confirmation_text": "delete"},  # wrong case
    )
    assert response.status_code == 400
    assert executed is False

    # Exact match — now it actually runs.
    response = await client.post(
        f"/conversations/{created['id']}/messages/{sent['id']}/confirm-action",
        json={"confirmation_text": "DELETE"},
    )
    assert response.status_code == 200
    assert executed is True


async def test_confirm_action_404_when_message_has_no_proposal(client):
    created = (await client.post("/conversations", json={})).json()
    sent = (
        await client.post(f"/conversations/{created['id']}/messages", json={"content": "hi"})
    ).json()

    response = await client.post(
        f"/conversations/{created['id']}/messages/{sent['id']}/confirm-action"
    )
    assert response.status_code == 404


async def _propose_and_confirm(client, monkeypatch, proposed_action: dict, message: str = "go"):
    async def _fake_with_proposal(history, company_id, session, user):
        return ("ok", [], True, proposed_action, [])

    monkeypatch.setattr(chat_module, "run_chat_turn", _fake_with_proposal)

    created = (await client.post("/conversations", json={})).json()
    sent = (
        await client.post(f"/conversations/{created['id']}/messages", json={"content": message})
    ).json()
    return await client.post(f"/conversations/{created['id']}/messages/{sent['id']}/confirm-action")


async def test_confirm_action_auto_resolves_company_when_omitted(
    client, monkeypatch, seeded_company
):
    """create_content_plan is in _COMPANY_AUTO_RESOLVABLE_WRITE_TOOLS — with
    exactly one accessible company, the security check should resolve it
    the same way the tool implementation's own fallback would, not refuse
    the whole action just because Claude left company_id out (this is the
    normal case for a company-less conversation, the default kind in this
    single-company-focused app)."""
    executed_with: dict = {}

    async def _fake_create_plan(session, **kwargs):
        executed_with.update(kwargs)
        return "Started generating a new content plan."

    monkeypatch.setitem(chat_module.WRITE_TOOL_IMPLEMENTATIONS, "create_content_plan", _fake_create_plan)

    proposed_action = {
        "tool_name": "create_content_plan",
        "tool_input": {},  # no company_id — exactly what Claude sends when none was named
        "description": "Create a new content plan",
    }
    response = await _propose_and_confirm(client, monkeypatch, proposed_action)

    assert response.status_code == 200
    assert executed_with["company_id"] == str(seeded_company)


async def test_confirm_action_400s_when_no_company_to_auto_resolve(client, monkeypatch):
    proposed_action = {
        "tool_name": "create_content_plan",
        "tool_input": {},
        "description": "Create a new content plan",
    }
    response = await _propose_and_confirm(client, monkeypatch, proposed_action)

    assert response.status_code == 400
    assert "No onboarded company" in response.json()["detail"]


async def test_confirm_action_400s_when_multiple_companies_are_accessible(
    client, monkeypatch, seeded_company, test_session_factory
):
    async with test_session_factory() as session:
        session.add(Company(id=uuid.uuid4(), url="https://example.org", status="complete"))
        await session.commit()

    proposed_action = {
        "tool_name": "create_content_plan",
        "tool_input": {},
        "description": "Create a new content plan",
    }
    response = await _propose_and_confirm(client, monkeypatch, proposed_action)

    assert response.status_code == 400
    assert "More than one company" in response.json()["detail"]


async def test_confirm_action_still_refuses_a_tool_with_no_identifiable_target(
    client, monkeypatch, seeded_company
):
    """Only tools explicitly opted into _COMPANY_AUTO_RESOLVABLE_WRITE_TOOLS
    get the auto-resolve fallback — a real, registered write tool
    (approve_content_item) with neither company_id nor content_item_id in
    tool_input still hits the original hard refusal, unweakened. Guards
    against silently loosening this for every write tool by accident."""
    proposed_action = {
        "tool_name": "approve_content_item",
        "tool_input": {},  # malformed on purpose — no content_item_id
        "description": "Approve something",
    }
    response = await _propose_and_confirm(client, monkeypatch, proposed_action)

    assert response.status_code == 400
    assert response.json()["detail"] == "This action's target could not be authorized"


async def test_confirm_action_409_when_already_resolved(
    client, monkeypatch, seeded_content_item
):
    proposed_action = {
        "tool_name": "approve_content_item",
        "tool_input": {"content_item_id": str(seeded_content_item)},
        "description": "Approve the content item",
    }

    async def _fake_with_proposal(history, company_id, session, user):
        return ("I'll approve that.", [], True, proposed_action, [])

    monkeypatch.setattr(chat_module, "run_chat_turn", _fake_with_proposal)

    async def _fake_approve(session, **kwargs):
        return "done"

    monkeypatch.setitem(chat_module.WRITE_TOOL_IMPLEMENTATIONS, "approve_content_item", _fake_approve)

    created = (await client.post("/conversations", json={})).json()
    sent = (
        await client.post(
            f"/conversations/{created['id']}/messages", json={"content": "approve it"}
        )
    ).json()

    await client.post(f"/conversations/{created['id']}/messages/{sent['id']}/confirm-action")
    response = await client.post(
        f"/conversations/{created['id']}/messages/{sent['id']}/confirm-action"
    )
    assert response.status_code == 409


async def _bump_created_at(test_session_factory, message_id: str, delta: timedelta) -> None:
    """Forces a message's `created_at` forward by `delta`. The in-memory
    SQLite test DB's `func.now()` only has second-level granularity (real
    Postgres has microsecond precision), so two messages created moments
    apart in a fast test can tie on `created_at` — this makes "is there a
    newer message" deterministic in tests without depending on real wall-
    clock gaps."""
    async with test_session_factory() as session:
        message = (
            await session.execute(select(ChatMessage).where(ChatMessage.id == uuid.UUID(message_id)))
        ).scalar_one()
        message.created_at = datetime.now(timezone.utc) + delta
        await session.commit()


async def test_confirm_action_409_when_a_newer_message_exists(
    client, monkeypatch, seeded_content_item, test_session_factory
):
    """A pending proposal stops being confirmable once the conversation has
    moved on — otherwise a stale card left dangling (e.g. by an earlier
    crash that never flipped its action_status) stays clickable forever,
    and confirming it later can mean executing a duplicate of something
    that's already effectively been handled. Confirmed against a real bug:
    a crash mid-confirm left a message stuck `pending` even though the
    underlying job had already succeeded; without this check that message
    stayed re-confirmable indefinitely."""
    proposed_action = {
        "tool_name": "approve_content_item",
        "tool_input": {"content_item_id": str(seeded_content_item)},
        "description": "Approve the content item",
    }

    async def _fake_with_proposal(history, company_id, session, user):
        return ("I'll approve that.", [], True, proposed_action, [])

    monkeypatch.setattr(chat_module, "run_chat_turn", _fake_with_proposal)

    created = (await client.post("/conversations", json={})).json()
    sent = (
        await client.post(
            f"/conversations/{created['id']}/messages", json={"content": "approve it"}
        )
    ).json()

    # Conversation continues past the still-unresolved proposal.
    async def _fake_no_proposal(history, company_id, session, user):
        return ("Sure, what else?", [], True, None, [])

    monkeypatch.setattr(chat_module, "run_chat_turn", _fake_no_proposal)
    later = (
        await client.post(
            f"/conversations/{created['id']}/messages", json={"content": "something else"}
        )
    ).json()
    await _bump_created_at(test_session_factory, later["id"], timedelta(seconds=5))

    response = await client.post(
        f"/conversations/{created['id']}/messages/{sent['id']}/confirm-action"
    )
    assert response.status_code == 409
    assert "expired" in response.json()["detail"].lower()


async def test_cancel_action_409_when_a_newer_message_exists(client, monkeypatch, test_session_factory):
    """Same expiry rule applies to cancel, not just confirm — an expired
    card is inert either way, not just non-executable."""
    proposed_action = {
        "tool_name": "approve_content_item",
        "tool_input": {"content_item_id": "abc-123"},
        "description": "Approve content item abc-123",
    }

    async def _fake_with_proposal(history, company_id, session, user):
        return ("I'll approve that.", [], True, proposed_action, [])

    monkeypatch.setattr(chat_module, "run_chat_turn", _fake_with_proposal)

    created = (await client.post("/conversations", json={})).json()
    sent = (
        await client.post(
            f"/conversations/{created['id']}/messages", json={"content": "approve it"}
        )
    ).json()

    async def _fake_no_proposal(history, company_id, session, user):
        return ("Sure, what else?", [], True, None, [])

    monkeypatch.setattr(chat_module, "run_chat_turn", _fake_no_proposal)
    later = (
        await client.post(
            f"/conversations/{created['id']}/messages", json={"content": "something else"}
        )
    ).json()
    await _bump_created_at(test_session_factory, later["id"], timedelta(seconds=5))

    response = await client.post(
        f"/conversations/{created['id']}/messages/{sent['id']}/cancel-action"
    )
    assert response.status_code == 409


async def test_history_sent_to_claude_is_annotated_with_action_status(
    client, monkeypatch, seeded_content_item
):
    """`_history_content` must tell the model what actually happened to its
    own earlier proposal — otherwise a still-pending (or already-resolved)
    proposal reads as an open question forever, which is what led Claude to
    re-propose an already-uploaded video verbatim in a real conversation
    instead of noticing the user had moved on to something new."""
    proposed_action = {
        "tool_name": "approve_content_item",
        "tool_input": {"content_item_id": str(seeded_content_item)},
        "description": "Approve the content item",
    }

    async def _fake_with_proposal(history, company_id, session, user):
        return ("Here's the proposal.", [], True, proposed_action, [])

    monkeypatch.setattr(chat_module, "run_chat_turn", _fake_with_proposal)
    created = (await client.post("/conversations", json={})).json()
    await client.post(f"/conversations/{created['id']}/messages", json={"content": "approve it"})

    seen_history: list[dict] = []

    async def _fake_capture_history(history, company_id, session, user):
        seen_history.extend(history)
        return ("noted", [], True, None, [])

    monkeypatch.setattr(chat_module, "run_chat_turn", _fake_capture_history)
    await client.post(f"/conversations/{created['id']}/messages", json={"content": "anything else?"})

    assistant_turn = next(m for m in seen_history if m["role"] == "assistant")
    assert "still awaiting the user's confirmation" in assistant_turn["content"]


def test_redact_internal_config_mentions_scrubs_env_var_names_and_env_file():
    """Regression test for a real leak: two messages written before a
    'not configured' error's wording was sanitized still had the raw old
    text ("...set COMPOSIO_API_KEY ... in .env") sitting in the DB, and —
    because every turn resends every prior message verbatim — Claude kept
    paraphrasing that old text back to the user on much later, unrelated
    turns, unprompted. This must catch it regardless of when the message
    was originally written, not just prevent new ones."""
    leaked = (
        "Publishing 'Ghibli-style whimsical AI art post' failed: instagram "
        "publishing is not configured — set COMPOSIO_API_KEY and its Composio "
        "post tool slug in .env"
    )
    redacted = chat_module._redact_internal_config_mentions(leaked)

    assert "COMPOSIO_API_KEY" not in redacted
    assert ".env" not in redacted
    assert "[internal config]" in redacted
    # A real caption shouldn't get mangled just for containing an
    # unrelated all-caps word or two.
    normal = "SHIP IT — our MVP is live! #BuildInPublic"
    assert chat_module._redact_internal_config_mentions(normal) == normal


async def test_history_sent_to_claude_has_a_past_leak_redacted(client, monkeypatch):
    """Same scenario as the unit test above, exercised end-to-end through
    the actual history-building path a real conversation uses."""
    leaked_text = (
        "Publishing failed: instagram publishing is not configured — set "
        "COMPOSIO_API_KEY and its Composio post tool slug in .env"
    )

    async def _fake_leaked_reply(history, company_id, session, user):
        return (leaked_text, [], True, None, [])

    monkeypatch.setattr(chat_module, "run_chat_turn", _fake_leaked_reply)
    created = (await client.post("/conversations", json={})).json()
    await client.post(f"/conversations/{created['id']}/messages", json={"content": "publish it"})

    seen_history: list[dict] = []

    async def _fake_capture_history(history, company_id, session, user):
        seen_history.extend(history)
        return ("noted", [], True, None, [])

    monkeypatch.setattr(chat_module, "run_chat_turn", _fake_capture_history)
    await client.post(f"/conversations/{created['id']}/messages", json={"content": "try again"})

    assistant_turn = next(m for m in seen_history if m["role"] == "assistant")
    assert "COMPOSIO_API_KEY" not in assistant_turn["content"]
    assert ".env" not in assistant_turn["content"]


async def test_cancel_action_marks_cancelled_without_executing(client, monkeypatch):
    proposed_action = {
        "tool_name": "approve_content_item",
        "tool_input": {"content_item_id": "abc-123"},
        "description": "Approve content item abc-123",
    }

    async def _fake_with_proposal(history, company_id, session, user):
        return ("I'll approve that.", [], True, proposed_action, [])

    monkeypatch.setattr(chat_module, "run_chat_turn", _fake_with_proposal)

    executed = False

    async def _fake_approve(session, **kwargs):
        nonlocal executed
        executed = True
        return "should not run"

    monkeypatch.setitem(chat_module.WRITE_TOOL_IMPLEMENTATIONS, "approve_content_item", _fake_approve)

    created = (await client.post("/conversations", json={})).json()
    sent = (
        await client.post(
            f"/conversations/{created['id']}/messages", json={"content": "approve it"}
        )
    ).json()

    response = await client.post(
        f"/conversations/{created['id']}/messages/{sent['id']}/cancel-action"
    )
    assert response.status_code == 200
    assert response.json()["action_status"] == "cancelled"
    assert executed is False


class _FakeUploadBucket:
    def __init__(self):
        self.uploaded: list[tuple] = []

    async def upload(self, path, data, file_options=None):
        self.uploaded.append((path, data, file_options))

    async def get_public_url(self, path):
        return f"https://fake.supabase.co/{path}"


def _mock_storage_client(monkeypatch) -> _FakeUploadBucket:
    """Wires chat_module._client/_require_configured to a fake bucket so
    /attachments can be tested without a real Supabase Storage account."""
    bucket = _FakeUploadBucket()

    class _FakeStorageClient:
        def from_(self, bucket_name):
            return bucket

    class _FakeSupabaseClient:
        storage = _FakeStorageClient()

    async def _fake_client():
        return _FakeSupabaseClient()

    monkeypatch.setattr(chat_module, "_client", _fake_client)
    monkeypatch.setattr(chat_module, "_require_configured", lambda: None)
    return bucket


async def test_upload_chat_attachment_converts_heic_to_jpeg(client, monkeypatch):
    """Regression test for a real bug: a HEIC upload (an iPhone's default
    photo format) rendered as a broken image in the chat UI — no browser
    decodes HEIC natively. Confirmed live via a real chat attachment."""
    bucket = _mock_storage_client(monkeypatch)
    monkeypatch.setattr(chat_module, "convert_heic_to_jpeg", lambda content: b"converted-jpeg-bytes")

    response = await client.post(
        "/attachments",
        files={"file": ("IMG_1762.HEIC", b"fake heic bytes", "image/heic")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "IMG_1762.jpg"
    assert body["content_type"] == "image/jpeg"
    assert body["size_bytes"] == len(b"converted-jpeg-bytes")
    assert bucket.uploaded[0][2] == {"content-type": "image/jpeg"}


async def test_upload_chat_attachment_leaves_ordinary_images_untouched(client, monkeypatch):
    bucket = _mock_storage_client(monkeypatch)

    response = await client.post(
        "/attachments",
        files={"file": ("photo.jpg", b"real jpeg bytes", "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "photo.jpg"
    assert body["content_type"] == "image/jpeg"
    assert bucket.uploaded[0][1] == b"real jpeg bytes"


async def test_upload_chat_attachment_422s_on_an_unreadable_heic_file(client, monkeypatch):
    _mock_storage_client(monkeypatch)

    def _raise(content):
        raise ValueError("cannot identify image file")

    monkeypatch.setattr(chat_module, "convert_heic_to_jpeg", _raise)

    response = await client.post(
        "/attachments",
        files={"file": ("broken.heic", b"not really an image", "image/heic")},
    )

    assert response.status_code == 422
