"""owner_id / user_id scoping

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-05

Fixes KNOWN_ISSUES.md C2 ("any signed-in user can read and modify every
client's data"): adds `companies.owner_id` (the Supabase user id that
onboarded the company) and `chat_conversations.user_id` (the Supabase
user id that started the conversation — set directly rather than
derived from company_id, since a conversation's company_id is nullable).

Both columns are nullable so existing rows don't break: they were
created before per-user ownership existed, so there's no real owner to
backfill. The application layer treats a null owner as "unclaimed" —
inaccessible going forward, not silently shared — see
app/security/ownership.py.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("owner_id", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_companies_owner_id"), "companies", ["owner_id"])

    op.add_column("chat_conversations", sa.Column("user_id", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_chat_conversations_user_id"), "chat_conversations", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_conversations_user_id"), table_name="chat_conversations")
    op.drop_column("chat_conversations", "user_id")

    op.drop_index(op.f("ix_companies_owner_id"), table_name="companies")
    op.drop_column("companies", "owner_id")
