"""API tests for the intelligent chat routes."""

from __future__ import annotations

import uuid
from datetime import date

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.agents.chat import agent as agent_module
from app.api.v1.endpoints import chat as chat_module
from app.db.models import Company, ContentItem, ContentPlan
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
    async def _fake_run_chat_turn(history, company_id, session):
        return ("Fake assistant reply.", ["list_trending_topics"], True, None, [])

    async def _fake_generate_conversation_title(user_message):
        if user_message == "trigger-title-failure":
            return None
        return f"Title for: {user_message}"

    monkeypatch.setattr(chat_module, "run_chat_turn", _fake_run_chat_turn)
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

    async def _fake_with_proposal(history, company_id, session):
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


async def test_confirm_action_404_when_message_has_no_proposal(client):
    created = (await client.post("/conversations", json={})).json()
    sent = (
        await client.post(f"/conversations/{created['id']}/messages", json={"content": "hi"})
    ).json()

    response = await client.post(
        f"/conversations/{created['id']}/messages/{sent['id']}/confirm-action"
    )
    assert response.status_code == 404


async def test_confirm_action_409_when_already_resolved(
    client, monkeypatch, seeded_content_item
):
    proposed_action = {
        "tool_name": "approve_content_item",
        "tool_input": {"content_item_id": str(seeded_content_item)},
        "description": "Approve the content item",
    }

    async def _fake_with_proposal(history, company_id, session):
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


async def test_cancel_action_marks_cancelled_without_executing(client, monkeypatch):
    proposed_action = {
        "tool_name": "approve_content_item",
        "tool_input": {"content_item_id": "abc-123"},
        "description": "Approve content item abc-123",
    }

    async def _fake_with_proposal(history, company_id, session):
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
