"""Intelligent Chat routes: conversation CRUD + sending a message to the
tool-using chat agent (`app/agents/chat/agent.py`).
"""

from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.chat.agent import generate_conversation_title, run_chat_turn
from app.agents.chat.tools import WRITE_TOOL_IMPLEMENTATIONS
from app.agents.media_library.storage import (
    MediaLibraryNotConfiguredError,
    _client,
    _require_configured,
)
from app.config import settings
from app.db.models import ChatConversation, ChatMessage
from app.db.session import get_session
from app.models.chat import (
    AttachmentUploadResponse,
    ChatMessageOut,
    ConversationCreateRequest,
    ConversationDetailOut,
    ConversationListResponse,
    ConversationOut,
    SendMessageRequest,
)
from app.security.auth import CurrentUser, get_current_user
from app.security.ownership import get_owned_company

router = APIRouter(dependencies=[Depends(get_current_user)])

_TITLE_MAX_LEN = 80

# Bucket for chat attachments — separate prefix from media-library assets
# so they don't show up in company media libraries.
_CHAT_BUCKET = "chat-attachments"
_CHAT_MAX_BYTES = 20_000_000  # 20 MB, same cap as media library


@router.post("/attachments", response_model=AttachmentUploadResponse)
async def upload_chat_attachment(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> AttachmentUploadResponse:
    """Upload a file for use in a chat message. Stores it in Supabase
    Storage under `chat-attachments/{user_id}/` and returns a public URL
    the frontend embeds in the message content so the AI can reference it.
    No DB row is written — the URL lives in the message content itself."""
    try:
        _require_configured()
    except MediaLibraryNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    content_bytes = await file.read()
    if len(content_bytes) > _CHAT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds maximum upload size (20 MB)")

    safe_filename = file.filename or f"upload-{uuid.uuid4()}"
    content_type = file.content_type or "application/octet-stream"
    storage_path = f"{current_user.id}/{uuid.uuid4()}-{safe_filename}"

    client = await _client()
    # Use the same media-library bucket with a chat-attachments/ prefix so
    # bucket creation stays a single one-time step; files are logically
    # separated by path prefix.
    bucket = client.storage.from_(settings.SUPABASE_STORAGE_BUCKET)
    await bucket.upload(storage_path, content_bytes, file_options={"content-type": content_type})
    public_url = await bucket.get_public_url(storage_path)

    return AttachmentUploadResponse(
        url=public_url,
        filename=safe_filename,
        content_type=content_type,
        size_bytes=len(content_bytes),
    )


@router.post("/conversations", response_model=ConversationOut)
async def create_conversation(
    payload: ConversationCreateRequest,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationOut:
    # A conversation scoped to a company must be scoped to *the caller's*
    # company — otherwise chat tools (run_chat_turn below) would read and
    # act on another user's company data via conversation.company_id.
    if payload.company_id is not None:
        await get_owned_company(session, payload.company_id, current_user)
    conversation = ChatConversation(
        id=uuid.uuid4(), company_id=payload.company_id, user_id=current_user.id
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return ConversationOut.model_validate(conversation)


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(
    company_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationListResponse:
    stmt = (
        select(ChatConversation)
        .where(ChatConversation.user_id == current_user.id)
        .order_by(ChatConversation.updated_at.desc())
    )
    if company_id is not None:
        stmt = stmt.where(ChatConversation.company_id == company_id)
    rows = (await session.execute(stmt)).scalars().all()
    return ConversationListResponse(items=[ConversationOut.model_validate(row) for row in rows])


async def _get_conversation_or_404(
    session: AsyncSession, conversation_id: uuid.UUID, current_user: CurrentUser
) -> ChatConversation:
    conversation = (
        await session.execute(
            select(ChatConversation)
            .options(selectinload(ChatConversation.messages))
            .where(
                ChatConversation.id == conversation_id,
                ChatConversation.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationDetailOut:
    conversation = await _get_conversation_or_404(session, conversation_id, current_user)
    return ConversationDetailOut.model_validate(conversation)


@router.delete("/conversations/{conversation_id}", response_model=ConversationOut)
async def delete_conversation(
    conversation_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> ConversationOut:
    conversation = await _get_conversation_or_404(session, conversation_id, current_user)
    result = ConversationOut.model_validate(conversation)
    await session.delete(conversation)
    await session.commit()
    return result


@router.post("/conversations/{conversation_id}/messages", response_model=ChatMessageOut)
async def send_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> ChatMessageOut:
    conversation = await _get_conversation_or_404(session, conversation_id, current_user)

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

    needs_title = conversation.title is None

    await session.commit()

    # Renaming the conversation from the raw first message to something
    # that reflects its actual intent (e.g. "hi what can you do" ->
    # "Exploring Assistant Capabilities") is a separate, cheap Claude call
    # — run it alongside the real turn instead of before it, so it never
    # adds latency to the reply the user is waiting on. It never touches
    # `session`, so it's safe to run concurrently with `run_chat_turn`
    # (which does).
    title_task = asyncio.create_task(generate_conversation_title(payload.content)) if needs_title else None

    text, tools_used, ok, proposed_action, cards = await run_chat_turn(
        history, conversation.company_id, session, current_user
    )

    if title_task is not None:
        generated_title = await title_task
        conversation.title = (generated_title or payload.content)[:_TITLE_MAX_LEN]

    assistant_message = ChatMessage(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role="assistant",
        content=text,
        tool_calls_summary=tools_used or None,
        proposed_action=proposed_action,
        action_status="pending" if proposed_action is not None else None,
        cards=cards or None,
    )
    session.add(assistant_message)
    await session.commit()
    await session.refresh(assistant_message)

    result = ChatMessageOut.model_validate(assistant_message)
    result.ok = ok
    return result


async def _get_pending_action_message(
    session: AsyncSession, conversation_id: uuid.UUID, message_id: uuid.UUID, current_user: CurrentUser
) -> ChatMessage:
    # Ownership lives on the conversation, not the message — resolving it
    # first (and 404ing the same way a missing conversation would) is what
    # stops another user from confirming/cancelling an action by guessing
    # a conversation_id/message_id pair.
    await _get_conversation_or_404(session, conversation_id, current_user)
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
    current_user: CurrentUser = Depends(get_current_user),
) -> ChatMessageOut:
    """Actually run a write tool the chat agent proposed. Nothing the chat
    agent proposes is ever executed until this endpoint is hit — this is
    the entire safety boundary for the agent's write tools."""
    message = await _get_pending_action_message(session, conversation_id, message_id, current_user)
    action = message.proposed_action
    impl = WRITE_TOOL_IMPLEMENTATIONS.get(action["tool_name"])
    if impl is None:
        raise HTTPException(status_code=500, detail=f"Unknown tool: {action['tool_name']}")

    result_text, result_cards = await impl(session, current_user, **action["tool_input"])
    message.action_status = "confirmed"
    await session.commit()

    result_message = ChatMessage(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role="assistant",
        content=result_text,
        cards=result_cards or None,
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
    current_user: CurrentUser = Depends(get_current_user),
) -> ChatMessageOut:
    message = await _get_pending_action_message(session, conversation_id, message_id, current_user)
    message.action_status = "cancelled"
    await session.commit()
    await session.refresh(message)
    return ChatMessageOut.model_validate(message)
