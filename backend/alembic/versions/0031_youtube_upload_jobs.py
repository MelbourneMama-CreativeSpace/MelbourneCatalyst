"""youtube upload jobs

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-09

Queues a real YouTube video upload as a retryable row instead of a
one-shot synchronous attempt — `run_scheduled_youtube_uploads` retries any
row still `pending` until it succeeds or hits `MAX_YOUTUBE_UPLOAD_ATTEMPTS`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    string_array_type = sa.JSON().with_variant(ARRAY(sa.String()), "postgresql")

    op.create_table(
        "youtube_upload_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "platform_connection_id",
            sa.Uuid(),
            sa.ForeignKey("platform_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("video_url", sa.String(), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("tags", string_array_type, nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("status_error", sa.String(), nullable=True),
        sa.Column("composio_execution_id", sa.String(length=128), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_youtube_upload_jobs_platform_connection_id",
        "youtube_upload_jobs",
        ["platform_connection_id"],
    )
    op.create_index("ix_youtube_upload_jobs_status", "youtube_upload_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_youtube_upload_jobs_status", table_name="youtube_upload_jobs")
    op.drop_index(
        "ix_youtube_upload_jobs_platform_connection_id", table_name="youtube_upload_jobs"
    )
    op.drop_table("youtube_upload_jobs")
