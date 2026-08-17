"""company members

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-06

Per-company authorization. Until now every route required a valid Supabase
session but nothing tied a Company to the user(s) allowed to touch it, so
any signed-in user could read/write/connect/disconnect any company's data.

Deliberately additive and non-destructive: no column is added to
`companies`, and no existing row is modified. Companies that predate this
migration have zero members, which the application layer treats as
"unclaimed" — the first signed-in user to access one becomes its owner.
That keeps this migration reversible and means no manual backfill step is
needed for data created before ownership existed.

History note: this started life as a second, competing `0027` alongside
`0027_owner_and_user_scoping`, which solved the same problem with a
`companies.owner_id` column instead. Two revisions sharing one id makes
Alembic pick one and silently skip the other, so `owner_and_user_scoping`
was applied to the database while this one never ran — leaving the code
querying a `company_members` table that did not exist. Renumbered to 0029
so the history is linear and this actually applies. `companies.owner_id`
is now dead weight (mapped in models.py, queried nowhere); dropping it is
left to a follow-up so this migration stays purely additive.

`chat_conversations.user_id` is NOT created here — `0027_owner_and_user_scoping`
already added it. It is only widened to match the ORM's String(128).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
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

    # Widen to the ORM's String(128). The column and its index already exist
    # from 0027_owner_and_user_scoping, which sized it at 64. A Supabase
    # `sub` is a 36-char UUID so 64 was never actually too small, but the
    # mismatch would surface as a confusing truncation error if the claim
    # format ever changed.
    op.alter_column(
        "chat_conversations",
        "user_id",
        existing_type=sa.String(length=64),
        type_=sa.String(length=128),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "chat_conversations",
        "user_id",
        existing_type=sa.String(length=128),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
    op.drop_index("ix_company_members_user_id", table_name="company_members")
    op.drop_index("ix_company_members_company_id", table_name="company_members")
    op.drop_table("company_members")
