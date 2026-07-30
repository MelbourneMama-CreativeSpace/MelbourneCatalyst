"""content draft workspace: content_item_revisions, content_item_comments

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-30

Version history (a snapshot of draft_copy taken before each change) and
comments on ContentItem, for the new per-platform Draft Workspace.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_item_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "content_item_id",
            sa.Uuid(),
            sa.ForeignKey("content_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("draft_copy", sa.String(), nullable=False),
        sa.Column("edited_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_content_item_revisions_content_item_id",
        "content_item_revisions",
        ["content_item_id"],
    )

    op.create_table(
        "content_item_comments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "content_item_id",
            sa.Uuid(),
            sa.ForeignKey("content_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author", sa.String(length=128), nullable=True),
        sa.Column("body", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_content_item_comments_content_item_id",
        "content_item_comments",
        ["content_item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_content_item_comments_content_item_id", table_name="content_item_comments")
    op.drop_table("content_item_comments")
    op.drop_index(
        "ix_content_item_revisions_content_item_id", table_name="content_item_revisions"
    )
    op.drop_table("content_item_revisions")
