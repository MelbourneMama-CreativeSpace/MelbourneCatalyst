"""Per-user ownership checks for company-scoped data.

Fixes KNOWN_ISSUES.md C2: `get_current_user` only proves *who* is calling,
not *what they're allowed to touch*. Every company-scoped route needs to
resolve a `company_id` through `get_owned_company` (or filter a list query
through `owned_company_ids`) instead of loading rows directly — the point
of a shared helper is that this can't silently be skipped in one endpoint
file the way nine copy-pasted `_get_company_or_404` helpers already were.

A `None` `owner_id` means the row predates ownership entirely (created
before this migration) — treated as unclaimed/inaccessible rather than
shared, since there's no real prior owner to defer to.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company
from app.security.auth import CurrentUser


async def get_owned_company(
    session: AsyncSession, company_id: uuid.UUID, current_user: CurrentUser
) -> Company:
    """Loads `company_id`, 404ing (not 403 — don't confirm the row exists
    to someone who doesn't own it) unless it belongs to `current_user`."""
    company = await session.get(Company, company_id)
    if company is None or company.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


async def owned_company_ids(session: AsyncSession, current_user: CurrentUser) -> list[uuid.UUID]:
    """All company ids `current_user` owns — for list endpoints that filter
    by an *optional* company_id and, when it's absent, must still scope to
    the caller instead of returning every company's rows."""
    rows = (
        await session.execute(select(Company.id).where(Company.owner_id == current_user.id))
    ).scalars().all()
    return list(rows)
