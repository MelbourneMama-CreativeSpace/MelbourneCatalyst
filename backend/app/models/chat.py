"""Pydantic response/request schemas for the intelligent chat API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID | None
    title: str | None
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationOut]


class ConversationCreateRequest(BaseModel):
    company_id: uuid.UUID | None = None


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    tool_calls_summary: list[str] | None
    proposed_action: dict | None
    action_status: str | None
    created_at: datetime
    # Only meaningful on assistant messages — False means this is a
    # graceful-degradation reply (e.g. no Claude credit), not a real
    # answer. Not a DB column: attached to the response at send-time.
    ok: bool | None = None


class ConversationDetailOut(ConversationOut):
    messages: list[ChatMessageOut]


class SendMessageRequest(BaseModel):
    content: str
