"""company description + optional url

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-07

Lets a company onboard without a website.

The niche that drives trend collection used to be typed into `.env`
(`GOOGLE_TRENDS_SEED_KEYWORDS` and friends); it now comes from each
company's extracted `niche_keywords`. That only works if every company can
actually be profiled, and not every business has a site to scrape — so
`companies.url` becomes nullable and `companies.description` is added to
hold the operator's own words as an alternative extraction input.

`url` keeps its UNIQUE constraint: Postgres permits any number of NULLs
under UNIQUE, so description-only companies coexist while URLs stay
de-duplicated. Widening NOT NULL -> NULL is not itself destructive and
needs no table rewrite.

The downgrade can only restore NOT NULL if no description-only company
exists by then; it deletes nothing, and raises instead so the operator
decides what happens to those rows rather than losing them silently.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("description", sa.String(), nullable=True))
    op.alter_column(
        "companies",
        "url",
        existing_type=sa.String(length=2048),
        nullable=True,
    )


def downgrade() -> None:
    connection = op.get_bind()
    orphaned = connection.execute(
        sa.text("SELECT COUNT(*) FROM companies WHERE url IS NULL")
    ).scalar_one()
    if orphaned:
        raise RuntimeError(
            f"{orphaned} company/companies were onboarded without a URL and cannot be "
            "made NOT NULL. Give them a url or delete them, then re-run this downgrade."
        )

    op.alter_column(
        "companies",
        "url",
        existing_type=sa.String(length=2048),
        nullable=False,
    )
    op.drop_column("companies", "description")
