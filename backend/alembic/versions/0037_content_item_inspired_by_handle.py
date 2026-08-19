"""content_items.inspired_by_handle

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-19

Real bug this fixes: content generated for/inspired by an external
account (looked up via analyze_social_profile -- a competitor, a
reference creator, a not-yet-onboarded client) had no way to be
distinguished from this company's own organic content once persisted --
same ContentPlan, same table, no marker at all. Confirmed live: a reel
idea written entirely in a different creator's voice and hashtags ended
up as a real ContentItem under this company's own pipeline, publishable
through this company's own connected accounts as if it were their own.

Nullable, additive -- null means "this company's own content", same as
every row before this migration.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_items", sa.Column("inspired_by_handle", sa.String(length=128), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("content_items", "inspired_by_handle")
