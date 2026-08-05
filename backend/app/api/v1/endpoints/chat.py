"""Intelligent Chat routes: conversation CRUD + sending a message to the
tool-using chat agent (`app/agents/chat/agent.py`).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.chat.agent import run_chat_turn
from app.agents.chat.tools import WRITE_TOOL_IMPLEMENTATIONS
from app.db.models import ChatConversation, ChatMessage, ContentItem, ContentPlan
from app.db.session import get_session
from app.models.chat import (
    ChatMessageOut,
    ConversationCreateRequest,
    ConversationDetailOut,
    ConversationListResponse,
    ConversationOut,
    SendMessageRequest,
)
from app.security.auth import CurrentUser, get_current_user
from app.security.ownership import ensure_company_access

router = APIRouter(dependencies=[Depends(get_current_user)])

_TITLE_MAX_LEN = 80


@router.post("/conversations", response_model=ConversationOut)
async def create_conversation(
    payload: ConversationCreateRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ConversationOut:
    if payload.company_id is not None:
        await ensure_company_access(session, payload.company_id, user)
    conversation = ChatConversation(
        id=uuid.uuid4(), company_id=payload.company_id, user_id=user.id
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return ConversationOut.model_validate(conversation)


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    company_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ConversationListResponse:
    # A conversation is private to the person who had it, not shared across
    # a company's members — chat transcripts read as personal working notes,
    # and nothing in the UI has ever presented them as team-visible.
    stmt = (
        select(ChatConversation)
        .where(
            (ChatConversation.user_id == user.id) | (ChatConversation.user_id.is_(None))
        )
        .order_by(ChatConversation.updated_at.desc())
    )
    if company_id is not None:
        stmt = stmt.where(ChatConversation.company_id == company_id)
    rows = (await session.execute(stmt)).scalars().all()
    return ConversationListResponse(items=[ConversationOut.model_validate(row) for row in rows])


async def _get_conversation_or_404(
    session: AsyncSession, conversation_id: uuid.UUID, user: CurrentUser
) -> ChatConversation:
    conversation = (
        await session.execute(
            select(ChatConversation)
            .options(selectinload(ChatConversation.messages))
            .where(ChatConversation.id == conversation_id)
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conversation.user_id is None:
        # Pre-ownership row — claimed by the first user to open it, same
        # transition rule as an unclaimed company.
        conversation.user_id = user.id
        await session.commit()
    elif conversation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Belt and braces: a conversation scoped to a company the user has
    # since been removed from shouldn't keep working just because they
    # started it.
    if conversation.company_id is not None:
        await ensure_company_access(session, conversation.company_id, user)
    return conversation


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ConversationDetailOut:
    conversation = await _get_conversation_or_404(session, conversation_id, user)
    return ConversationDetailOut.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", response_model=ConversationOut)
async def delete_conversation(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ConversationOut:
    conversation = await _get_conversation_or_404(session, conversation_id, user)
    result = ConversationOut.model_validate(conversation)
    await session.delete(conversation)
    await session.commit()
    return result


@router.post("/conversations/{conversation_id}/messages", response_model=ChatMessageOut)
async def send_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ChatMessageOut:
    conversation = await _get_conversation_or_404(session, conversation_id, user)

    # Build Claude-format history from prior messages before persisting the
    # new one, so the new user message ends up exactly once, in order.
    history = [{"role": m.role, "content": m.content} for m in conversation.messages]
    history.append({"role": "user", "content": payload.content})

    user_message = ChatMessage(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role="user",
        content=payload.content,
    )
    session.add(user_message)

    if conversation.title is None:
        conversation.title = payload.content[:_TITLE_MAX_LEN]

    await session.commit()

    text, tools_used, ok, proposed_action = await run_chat_turn(
        history, conversation.company_id, session
    )

    assistant_message = ChatMessage(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role="assistant",
        content=text,
        tool_calls_summary=tools_used or None,
        proposed_action=proposed_action,
        action_status="pending" if proposed_action is not None else None,
    )
    session.add(assistant_message)
    await session.commit()
    await session.refresh(assistant_message)

    result = ChatMessageOut.model_validate(assistant_message)
    result.ok = ok
    return result


async def _ensure_action_target_allowed(
    session: AsyncSession, action: dict, user: CurrentUser
) -> None:
    """Re-check ownership of whatever a proposed write tool would touch.

    The proposal was produced inside a conversation the caller owns, but
    the target id in `tool_input` came from Claude, from text the user
    typed — so it is not, by itself, evidence the caller may act on that
    row. Every write tool addresses either a content item or a company;
    both resolve to a company_id, which is re-checked here immediately
    before execution.
    """
    tool_input = action.get("tool_input") or {}

    raw_company_id = tool_input.get("company_id")
    if raw_company_id:
        try:
            company_id = uuid.UUID(str(raw_company_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid company id in proposed action")
        await ensure_company_access(session, company_id, user)
        return

    raw_item_id = tool_input.get("content_item_id")
    if raw_item_id:
        try:
            item_id = uuid.UUID(str(raw_item_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid content item id in proposed action")
        item = await session.get(ContentItem, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Content item not found")
        plan = await session.get(ContentPlan, item.content_plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Content item not found")
        await ensure_company_access(session, plan.company_id, user)
        return

    # A write tool that addresses neither is one this check doesn't know
    # how to authorize — refuse rather than execute it unchecked. This is
    # the branch a future write tool will hit if someone adds one without
    # extending this function, which is the intended failure mode.
    raise HTTPException(
        status_code=400,
        detail="This action's target could not be authorized",
    )


async def _get_pending_action_message(
    session: AsyncSession, conversation_id: uuid.UUID, message_id: uuid.UUID
) -> ChatMessage:
    message = (
        await session.execute(
            select(ChatMessage).where(
                ChatMessage.id == message_id, ChatMessage.conversation_id == conversation_id
            )
        )
    ).scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.proposed_action is None:
        raise HTTPException(status_code=404, detail="This message has no proposed action")
    if message.action_status != "pending":
        raise HTTPException(
            status_code=409, detail=f"This action is already {message.action_status}"
        )
    return message


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/confirm-action",
    response_model=ChatMessageOut,
)
async def confirm_action(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ChatMessageOut:
    """Actually run a write tool the chat agent proposed. Nothing the chat
    agent proposes is ever executed until this endpoint is hit — this is
    the entire safety boundary for the agent's write tools."""
    await _get_conversation_or_404(session, conversation_id, user)
    message = await _get_pending_action_message(session, conversation_id, message_id)
    action = message.proposed_action
    impl = WRITE_TOOL_IMPLEMENTATIONS.get(action["tool_name"])
    if impl is None:
        raise HTTPException(status_code=500, detail=f"Unknown tool: {action['tool_name']}")

    await _ensure_action_target_allowed(session, action, user)
    result_text = await impl(session, **action["tool_input"])
    message.action_status = "confirmed"
    await session.commit()

    result_message = ChatMessage(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role="assistant",
        content=result_text,
    )
    session.add(result_message)
    await session.commit()
    await session.refresh(message)

    return ChatMessageOut.model_validate(message)


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/cancel-action",
    response_model=ChatMessageOut,
)
async def cancel_action(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ChatMessageOut:
    await _get_conversation_or_404(session, conversation_id, user)
    message = await _get_pending_action_message(session, conversation_id, message_id)
    message.action_status = "cancelled"
    await session.commit()
    await session.refresh(message)
    return ChatMessageOut.model_validate(message)
