"""media assets

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-30

Media & Asset Library storage — one row per uploaded file, referencing
its Supabase Storage object by `storage_path`. Search this round is
tag/filename-based (no embedding column), per the standing scoping note
that keyword search alone is real day-one value.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    string_array_type = sa.JSON().with_variant(ARRAY(sa.String()), "postgresql")

    op.create_table(
        "media_assets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("public_url", sa.String(length=2048), nullable=True),
        sa.Column("tags", string_array_type, nullable=True),
        sa.Column("uploaded_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_media_assets_company_id", "media_assets", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_media_assets_company_id", table_name="media_assets")
    op.drop_table("media_assets")
