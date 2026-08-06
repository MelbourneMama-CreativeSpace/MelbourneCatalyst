"""company members

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-02

Per-company authorization. Until now every route required a valid Supabase
session but nothing tied a Company to the user(s) allowed to touch it, so
any signed-in user could read/write/connect/disconnect any company's data.

Deliberately additive and non-destructive: no column is added to
`companies`, and no existing row is modified. Companies that predate this
migration have zero members, which the application layer treats as
"unclaimed" — the first signed-in user to access one becomes its owner.
That keeps this migration reversible and means no manual backfill step is
needed for data created before ownership existed.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Supabase `sub` claim. Not a FK — auth.users lives in a schema this
        # app never touches. Nullable so a pending email invite can exist
        # before that person has ever signed in.
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("invited_email", sa.String(length=320), nullable=True),
        sa.Column("user_email", sa.String(length=320), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="owner"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "user_id", name="uq_company_members_company_user"),
        sa.UniqueConstraint("company_id", "invited_email", name="uq_company_members_company_email"),
    )
    op.create_index("ix_company_members_company_id", "company_members", ["company_id"])
    # Access checks filter by user_id far more often than by company, since
    # "which companies can I see" runs on every list/dashboard request.
    op.create_index("ix_company_members_user_id", "company_members", ["user_id"])

    # A chat conversation can be general (no company at all), so it can't
    # inherit ownership through `company_id` the way every other table
    # does — it needs the owning user directly. Nullable for the same
    # reason as above: pre-existing rows have no user to attribute them to.
    op.add_column(
        "chat_conversations", sa.Column("user_id", sa.String(length=128), nullable=True)
    )
    op.create_index("ix_chat_conversations_user_id", "chat_conversations", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_conversations_user_id", table_name="chat_conversations")
    op.drop_column("chat_conversations", "user_id")
    op.drop_index("ix_company_members_user_id", table_name="company_members")
    op.drop_index("ix_company_members_company_id", table_name="company_members")
    op.drop_table("company_members")
