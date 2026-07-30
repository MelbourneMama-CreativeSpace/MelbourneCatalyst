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
from app.db.models import ChatConversation, ChatMessage
from app.db.session import get_session
from app.models.chat import (
    ChatMessageOut,
    ConversationCreateRequest,
    ConversationDetailOut,
    ConversationListResponse,
    ConversationOut,
    SendMessageRequest,
)
from app.security.auth import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])

_TITLE_MAX_LEN = 80


@router.post("/conversations", response_model=ConversationOut)
async def create_conversation(
    payload: ConversationCreateRequest, session: AsyncSession = Depends(get_session)
) -> ConversationOut:
    conversation = ChatConversation(id=uuid.uuid4(), company_id=payload.company_id)
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return ConversationOut.model_validate(conversation)


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    company_id: uuid.UUID | None = None, session: AsyncSession = Depends(get_session)
) -> ConversationListResponse:
    stmt = select(ChatConversation).order_by(ChatConversation.updated_at.desc())
    if company_id is not None:
        stmt = stmt.where(ChatConversation.company_id == company_id)
    rows = (await session.execute(stmt)).scalars().all()
    return ConversationListResponse(items=[ConversationOut.model_validate(row) for row in rows])


async def _get_conversation_or_404(session: AsyncSession, conversation_id: uuid.UUID) -> ChatConversation:
    conversation = (
        await session.execute(
            select(ChatConversation)
            .options(selectinload(ChatConversation.messages))
            .where(ChatConversation.id == conversation_id)
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> ConversationDetailOut:
    conversation = await _get_conversation_or_404(session, conversation_id)
    return ConversationDetailOut.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", response_model=ConversationOut)
async def delete_conversation(
    conversation_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> ConversationOut:
    conversation = await _get_conversation_or_404(session, conversation_id)
    result = ConversationOut.model_validate(conversation)
    await session.delete(conversation)
    await session.commit()
    return result


@router.post("/conversations/{conversation_id}/messages", response_model=ChatMessageOut)
async def send_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatMessageOut:
    conversation = await _get_conversation_or_404(session, conversation_id)

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
) -> ChatMessageOut:
    """Actually run a write tool the chat agent proposed. Nothing the chat
    agent proposes is ever executed until this endpoint is hit — this is
    the entire safety boundary for the agent's write tools."""
    message = await _get_pending_action_message(session, conversation_id, message_id)
    action = message.proposed_action
    impl = WRITE_TOOL_IMPLEMENTATIONS.get(action["tool_name"])
    if impl is None:
        raise HTTPException(status_code=500, detail=f"Unknown tool: {action['tool_name']}")

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
) -> ChatMessageOut:
    message = await _get_pending_action_message(session, conversation_id, message_id)
    message.action_status = "cancelled"
    await session.commit()
    await session.refresh(message)
    return ChatMessageOut.model_validate(message)
