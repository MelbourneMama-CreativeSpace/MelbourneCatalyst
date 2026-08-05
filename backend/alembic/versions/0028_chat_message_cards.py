"""chat message cards

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-06

Adds a `cards` column to chat_messages: small structured snapshots (a
content item just created/found, a trend surfaced) that the frontend
renders as flashcards inline in the chat, instead of the assistant only
ever describing things in prose. Purely additive/display — never replayed
back to Claude, same "display-only" contract `tool_calls_summary` already
has.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata_type = sa.JSON().with_variant(JSONB(), "postgresql")
    op.add_column("chat_messages", sa.Column("cards", metadata_type, nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "cards")
