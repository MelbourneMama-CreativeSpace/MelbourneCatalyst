"""chat message proposed actions

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-30

Adds propose-then-confirm support to the chat agent: a write-tool call
(approve/reject/regenerate/create) never executes inside the chat loop —
it's stored here as a proposal and only runs when the user hits confirm.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata_type = sa.JSON().with_variant(JSONB(), "postgresql")

    op.add_column("chat_messages", sa.Column("proposed_action", metadata_type, nullable=True))
    op.add_column("chat_messages", sa.Column("action_status", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "action_status")
    op.drop_column("chat_messages", "proposed_action")
