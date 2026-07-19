"""social media analyzer: platform_connections, platform_metric_snapshots

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-19

Creates platform_connections (OAuth connection state per company per
platform — tokens stored encrypted at the application layer, never
plaintext) and platform_metric_snapshots (storage shape for a future
Performance Tracking sync writer; no writer exists yet this round). No
dialect-specific types needed for platform_connections; raw_metadata on
platform_metric_snapshots reuses the same JSON/JSONB variant pattern as
Trend.raw_metadata.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata_type = sa.JSON().with_variant(JSONB(), "postgresql")

    op.create_table(
        "platform_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="disconnected"),
        sa.Column("status_error", sa.String(), nullable=True),
        sa.Column("access_token_encrypted", sa.String(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.String(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_account_id", sa.String(length=256), nullable=True),
        sa.Column("external_account_name", sa.String(length=256), nullable=True),
        sa.Column("scopes", sa.String(), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "company_id", "platform", name="uq_platform_connections_company_platform"
        ),
    )
    op.create_index("ix_platform_connections_company_id", "platform_connections", ["company_id"])
    op.create_index("ix_platform_connections_platform", "platform_connections", ["platform"])
    op.create_index("ix_platform_connections_status", "platform_connections", ["status"])

    op.create_table(
        "platform_metric_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "platform_connection_id",
            sa.Uuid(),
            sa.ForeignKey("platform_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("follower_count", sa.Integer(), nullable=True),
        sa.Column("engagement_rate", sa.Float(), nullable=True),
        sa.Column("raw_metadata", metadata_type, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_platform_metric_snapshots_platform_connection_id",
        "platform_metric_snapshots",
        ["platform_connection_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_metric_snapshots_platform_connection_id",
        table_name="platform_metric_snapshots",
    )
    op.drop_table("platform_metric_snapshots")
    op.drop_index("ix_platform_connections_status", table_name="platform_connections")
    op.drop_index("ix_platform_connections_platform", table_name="platform_connections")
    op.drop_index("ix_platform_connections_company_id", table_name="platform_connections")
    op.drop_table("platform_connections")
