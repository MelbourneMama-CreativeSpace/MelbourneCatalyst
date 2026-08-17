"""Intelligent Chat routes: conversation CRUD + sending a message to the
tool-using chat agent (`app/agents/chat/agent.py`).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.chat.agent import generate_conversation_title, run_chat_turn, run_chat_turn_stream
from app.agents.chat.tools import WRITE_TOOL_IMPLEMENTATIONS
from app.agents.media_library.image_conversion import (
    convert_heic_to_jpeg,
    heic_safe_filename,
    is_heic,
)
from app.agents.media_library.storage import (
    MediaLibraryNotConfiguredError,
    _client,
    _require_configured,
)
from app.config import settings
from app.db.models import ChatConversation, ChatMessage, Company, ContentItem, ContentPlan
from app.db.session import get_session
from app.models.chat import (
    AttachmentUploadResponse,
    ChatMessageOut,
    ConfirmActionRequest,
    ConversationCreateRequest,
    ConversationDetailOut,
    ConversationListResponse,
    ConversationOut,
    SendMessageRequest,
)
from app.security.auth import CurrentUser, get_current_user
from app.security.ownership import accessible_company_clause, ensure_company_access

router = APIRouter(dependencies=[Depends(get_current_user)])

_TITLE_MAX_LEN = 80

# Defense-in-depth against a leak living permanently in a conversation's
# own history. Every turn re-sends every prior message verbatim (see
# `_history_content` below) — a message written *before* a "not
# configured" error's wording was sanitized to stop naming env vars still
# has the old text sitting in the DB, and Claude reads that on every
# future turn regardless of what today's system prompt says. Confirmed
# live: two such old messages ("...set COMPOSIO_API_KEY ... in .env")
# caused a much later reply to spontaneously paraphrase "missing Composio
# API setup" back to the user, unprompted. Scrubbed here, on the read
# side, so every conversation — past and future, this one included — is
# protected without a data migration per already-affected row. Matches
# real env var *names* (KEY/SECRET/TOKEN/PASSWORD/CONFIG_ID suffixes,
# this codebase's actual naming convention — see .env.example) and
# literal ".env" mentions; deliberately never anything else, so this
# can't accidentally eat unrelated all-caps content in a real draft.
_SENSITIVE_CONFIG_NAME_PATTERN = re.compile(
    r"\b[A-Z][A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|CONFIG_ID)\b"
)
_ENV_FILE_MENTION_PATTERN = re.compile(r"\.env\b")


def _redact_internal_config_mentions(text: str) -> str:
    text = _SENSITIVE_CONFIG_NAME_PATTERN.sub("[internal config]", text)
    return _ENV_FILE_MENTION_PATTERN.sub("[internal config]", text)


def _history_content(message: ChatMessage) -> str:
    """One prior message's content for Claude, annotated with what actually
    happened to any proposed action attached to it. Without this, an
    assistant message that proposed a write action (e.g. "Here's what I'll
    upload: ...") reads to the *next* turn's model as an open-ended,
    unresolved statement — there is nothing in the plain text telling it
    apart from "the user confirmed this and it already ran" or "the user
    cancelled it". Confirmed live: with an actually-pending proposal sitting
    a few turns back (a crash had left `action_status` stuck at "pending"
    even though the underlying job had already succeeded), Claude re-issued
    that exact same proposal — same video, same title — instead of acting
    on a brand new video the user had just attached, apparently reading its
    own earlier, status-less proposal text as still the "current" thing to
    finish. Explicit status annotations close that gap."""
    content = _redact_internal_config_mentions(message.content)
    if message.proposed_action is not None:
        if message.action_status == "confirmed":
            content += (
                "\n\n[This action was confirmed by the user and has already "
                "executed. Do not propose it again.]"
            )
        elif message.action_status == "cancelled":
            content += "\n\n[The user cancelled this proposed action. It did not run.]"
        elif message.action_status == "pending":
            content += (
                "\n\n[This action is still awaiting the user's confirmation via "
                "the UI. Do not repeat or re-propose it — if the user's next "
                "message describes something different, propose that instead.]"
            )
    return content

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

    # HEIC (an iPhone's default photo format) renders as a broken image
    # in every major browser and isn't accepted by Facebook/Instagram's
    # photo-post APIs either — converted to JPEG here so both the chat
    # preview and a later publish just work, instead of failing later in
    # two different places for the same underlying reason.
    if is_heic(safe_filename, content_type):
        try:
            content_bytes = await asyncio.to_thread(convert_heic_to_jpeg, content_bytes)
        except Exception as exc:
            raise HTTPException(
                status_code=422, detail=f"Couldn't read that HEIC image: {exc}"
            ) from None
        safe_filename = heic_safe_filename(safe_filename)
        content_type = "image/jpeg"

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
    history = [{"role": m.role, "content": _history_content(m)} for m in conversation.messages]
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
        history, conversation.company_id, session, user
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


@router.post("/conversations/{conversation_id}/messages/stream")
async def send_message_stream(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """SSE endpoint — streams the assistant reply token by token.

    Each event is a ``data: <json>\\n\\n`` line.  Event shapes:
    - ``{"type": "token",  "text": "..."}``          — one raw text chunk
    - ``{"type": "tool",   "name": "..."}``           — tool being called
    - ``{"type": "done",   "message": <ChatMessageOut>}``  — full saved msg
    - ``{"type": "error",  "text": "..."}``           — something went wrong

    The frontend accumulates tokens into a live bubble; on "done" it
    replaces the bubble with the persisted ChatMessageOut so IDs and
    metadata are consistent.
    """
    conversation = await _get_conversation_or_404(session, conversation_id, user)

    history = [{"role": m.role, "content": _history_content(m)} for m in conversation.messages]
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

    title_task = (
        asyncio.create_task(generate_conversation_title(payload.content))
        if needs_title
        else None
    )

    async def _event_generator():
        accumulated = []
        tools_used = []
        proposed_action = None
        cards = []
        ok = True

        try:
            async for event_type, payload_data in run_chat_turn_stream(
                history, conversation.company_id, session, user
            ):
                if event_type == "token":
                    accumulated.append(payload_data)
                    yield f"data: {json.dumps({'type': 'token', 'text': payload_data})}\n\n"
                elif event_type == "tool":
                    tools_used.append(payload_data)
                    yield f"data: {json.dumps({'type': 'tool', 'name': payload_data})}\n\n"
                elif event_type == "done":
                    tools_used = payload_data.get("tools_used", tools_used)
                    proposed_action = payload_data.get("proposed_action")
                    cards = payload_data.get("cards", [])
                    ok = payload_data.get("ok", True)
                elif event_type == "error":
                    ok = False
                    accumulated = [payload_data]
                    yield f"data: {json.dumps({'type': 'error', 'text': payload_data})}\n\n"
        except Exception:
            ok = False
            accumulated = ["Something went wrong — try again."]
            yield f"data: {json.dumps({'type': 'error', 'text': accumulated[0]})}\n\n"

        # Persist the assistant message now that we have the full text
        full_text = "".join(accumulated)

        if title_task is not None:
            generated_title = await title_task
            # `conversation` was loaded before this generator started
            # running — by the time control actually reaches here,
            # FastAPI's `Depends(get_session)` teardown has already fired
            # (its cleanup runs as soon as `send_message_stream` *returns*
            # the `StreamingResponse` object, not once the streamed body
            # finishes — a well-known FastAPI/Starlette gotcha with
            # yield-dependencies + streaming responses). That teardown
            # calls `session.close()`, which detaches every previously
            # loaded object, `conversation` included — confirmed live via
            # `sqlalchemy.orm.object_session(conversation) is None` at
            # exactly this point. A `session.close()`'d session still
            # accepts brand-new objects via `.add()` just fine (which is
            # why `assistant_message` below always saved correctly, mask-
            # ing this bug), but a mutation on an already-detached object
            # is silently never flushed — every conversation's title
            # assignment here was being lost, permanently, which is also
            # why the sidebar's conversation history looked empty (it
            # filters to `title is not None`). Re-adding the object
            # reattaches it so this mutation actually gets committed.
            session.add(conversation)
            conversation.title = (generated_title or payload.content)[:_TITLE_MAX_LEN]

        assistant_message = ChatMessage(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            role="assistant",
            content=full_text,
            tool_calls_summary=tools_used or None,
            proposed_action=proposed_action,
            action_status="pending" if proposed_action is not None else None,
            cards=cards or None,
        )
        session.add(assistant_message)
        await session.commit()
        await session.refresh(assistant_message)

        msg_out = ChatMessageOut.model_validate(assistant_message)
        msg_out.ok = ok
        yield f"data: {json.dumps({'type': 'done', 'message': msg_out.model_dump(mode='json')})}\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )


# Write tools whose implementation already knows how to resolve "the one
# company" this user has access to when `company_id` is omitted (see
# `_resolve_company_id` in tools.py — the same fallback create_content_item
# and find_content_items use). For these, the exact same resolution
# happens here too, so this security check and the actual execution can
# never end up disagreeing about which company is being acted on. Any
# other write tool that addresses neither an explicit company nor a
# content item still hits the refusal at the bottom of
# `_ensure_action_target_allowed`, unchanged — this set opting a tool in
# is a deliberate choice per tool, not a default.
_COMPANY_AUTO_RESOLVABLE_WRITE_TOOLS = {"create_content_plan", "upload_youtube_video"}


async def _resolve_the_one_accessible_company(session: AsyncSession, user: CurrentUser) -> uuid.UUID:
    """The one `complete` company `user` has access to. Raises 400 if
    there isn't exactly one — same "don't guess, ask" stance as
    `tools.py`'s own `_resolve_company_id`, just enforced here too so a
    write action can never silently land on the wrong company."""
    companies = (
        await session.execute(
            select(Company.id).where(accessible_company_clause(user), Company.status == "complete")
        )
    ).scalars().all()
    if len(companies) == 1:
        return companies[0]
    raise HTTPException(
        status_code=400,
        detail=(
            "No onboarded company to authorize this against"
            if not companies
            else "More than one company is accessible — this action needs a specific company_id"
        ),
    )


async def _ensure_action_target_allowed(
    session: AsyncSession, action: dict, user: CurrentUser
) -> None:
    """Re-check ownership of whatever a proposed write tool would touch.

    The proposal was produced inside a conversation the caller owns, but
    the target id in `tool_input` came from Claude, from text the user
    typed — so it is not, by itself, evidence the caller may act on that
    row. Every write tool addresses a content item, an explicit company,
    or (only for tools in `_COMPANY_AUTO_RESOLVABLE_WRITE_TOOLS`) implicitly
    the one company `user` has access to — all three resolve to a
    company_id, which is re-checked here immediately before execution.
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

    if action.get("tool_name") in _COMPANY_AUTO_RESOLVABLE_WRITE_TOOLS:
        company_id = await _resolve_the_one_accessible_company(session, user)
        # Written back so the execution step right after this (which reads
        # action["tool_input"] again) resolves to the exact same company
        # this check just authorized, not a second independent lookup.
        tool_input["company_id"] = str(company_id)
        action["tool_input"] = tool_input
        return

    # A write tool that addresses none of the above is one this check
    # doesn't know how to authorize — refuse rather than execute it
    # unchecked. This is the branch a future write tool will hit if
    # someone adds one without extending this function, which is the
    # intended failure mode.
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
    # A proposal is only actionable while it's the newest thing in the
    # conversation. Once the user (or the assistant) has moved on — any
    # later message exists at all — this card is stale: re-confirming it
    # now could mean acting on something the conversation has since
    # superseded (a different video, a different item), or executing a
    # duplicate of a real-world action that already went through under a
    # separate proposal. Enforced server-side, not just hidden in the UI —
    # this is the actual safety boundary, same as the write tools
    # themselves only ever run from this endpoint.
    newer_message_exists = (
        await session.execute(
            select(ChatMessage.id).where(
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.created_at > message.created_at,
            )
        )
    ).first()
    if newer_message_exists is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "This proposal has expired — the conversation has moved on. "
                "Ask again if you'd still like to do this."
            ),
        )
    return message


@router.post(
    "/conversations/{conversation_id}/messages/{message_id}/confirm-action",
    response_model=ChatMessageOut,
)
async def confirm_action(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    payload: ConfirmActionRequest | None = None,
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

    # A handful of write tools (currently just delete_content_item_post)
    # are severe/irreversible enough to need more than the normal single
    # Confirm click — the proposal itself carries the exact phrase the
    # user must type, checked here server-side (the actual safety
    # boundary; the frontend disabling its own Confirm button until the
    # text matches is just the UX layer on top of this, not a substitute
    # for it).
    required_phrase = action.get("confirmation_phrase")
    if required_phrase and (payload is None or payload.confirmation_text != required_phrase):
        raise HTTPException(
            status_code=400,
            detail=f'Type "{required_phrase}" to confirm this action.',
        )

    await _ensure_action_target_allowed(session, action, user)
    tool_kwargs = dict(action["tool_input"])
    # Same opt-in-by-signature convention as the read-tool dispatcher
    # (`_execute_tool` in agent.py) — most write tools only need the ids
    # already in tool_input, but `create_content_plan` also needs `user`
    # to resolve an omitted company_id to "the" account's one company.
    if "user" in inspect.signature(impl).parameters:
        tool_kwargs.setdefault("user", user)
    result_text = await impl(session, **tool_kwargs)
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
