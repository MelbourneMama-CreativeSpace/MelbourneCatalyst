"""intelligent chat: chat_conversations, chat_messages

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-29

Storage for the new tool-using chat agent. `chat_conversations.company_id`
is nullable (a conversation can be scoped to one company or general) and
there is deliberately no `user_id` column — this app has no per-user data
isolation anywhere yet (see KNOWN_ISSUES.md), so chat follows the same
model as every other table rather than inventing a new isolation boundary
as a side effect of this feature. Only final user/assistant text is
persisted on chat_messages, not raw Anthropic tool_use/tool_result blocks.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    string_array_type = sa.JSON().with_variant(ARRAY(sa.String()), "postgresql")

    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_chat_conversations_company_id", "chat_conversations", ["company_id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("chat_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("tool_calls_summary", string_array_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_conversation_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_conversations_company_id", table_name="chat_conversations")
    op.drop_table("chat_conversations")
