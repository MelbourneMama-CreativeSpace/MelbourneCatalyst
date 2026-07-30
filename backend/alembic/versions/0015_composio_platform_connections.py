"""platform connections: switch to Composio-brokered OAuth

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-22

Replaces this app's own encrypted-token storage on `platform_connections`
with a reference to a Composio-hosted connected account — Composio now
custodies OAuth tokens, this backend never stores them (encrypted or
otherwise). See `app/agents/social_media_analyzer/` for the new flow.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_connections",
        sa.Column("composio_connected_account_id", sa.String(length=64), nullable=True),
    )
    op.drop_column("platform_connections", "access_token_encrypted")
    op.drop_column("platform_connections", "refresh_token_encrypted")
    op.drop_column("platform_connections", "token_expires_at")


def downgrade() -> None:
    op.add_column(
        "platform_connections", sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "platform_connections", sa.Column("refresh_token_encrypted", sa.String(), nullable=True)
    )
    op.add_column(
        "platform_connections", sa.Column("access_token_encrypted", sa.String(), nullable=True)
    )
    op.drop_column("platform_connections", "composio_connected_account_id")
