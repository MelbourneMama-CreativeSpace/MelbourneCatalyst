"""Per-company authorization — the half of the auth model that
`get_current_user` deliberately left open.

`get_current_user` proves *someone* is signed in. This module proves that
someone is allowed to touch *this particular company*. Every route that
reaches company-scoped data goes through `ensure_company_access`, which is
the single chokepoint: there is intentionally no second place that decides
who may see what.

Three behaviours worth knowing before changing anything here:

**404, never 403, for a company you're not a member of.** A 403 would
confirm the id exists, which turns an unguessable UUID into an oracle for
enumerating other tenants' companies. The response is byte-identical to a
genuinely-missing company.

**Claim-on-first-access.** A company with no resolved members is
*unclaimed* — the first signed-in user to access it becomes its owner. This
is a one-time transition affordance for the companies that already existed
before ownership did (there was no user to attribute them to, so there is
nothing to backfill from). Once claimed, normal membership rules apply
forever. Two teammates opening the same unclaimed company at the same
instant can both end up owners; that race is benign for a shared-team
account and isn't worth locking against.

**Pending email invites carry no access by themselves.** A row with only
`invited_email` set is inert until a token bearing that email address shows
up, at which point it binds to that user's real id. This is what lets
invites work without Supabase's Admin API — this app never needs to
translate an email into a user id, it just waits for the user to arrive.

**Scheduler jobs are deliberately unguarded, and must stay that way.**
`run_scheduled_reindex`, `run_scheduled_daily_reports`,
`run_scheduled_publishing`, `run_scheduled_metrics_sync`, trend collection,
and `run_onboarding` all run with no user at all — they legitimately sweep
every company. Enforcement lives at the API layer for exactly that reason.
Do not "tidy up" by pushing these checks down into the agent/graph modules:
that would break every background job the moment it ran.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Company, CompanyMember
from app.security.auth import CurrentUser

# Identical to the genuinely-missing-company message on purpose — see the
# module docstring. Don't make this more specific.
_NOT_FOUND = "Company not found"


def accessible_company_id_clause(
    user: CurrentUser, company_id_column: ColumnElement[uuid.UUID]
) -> ColumnElement[bool]:
    """A SQL predicate for "this row's company is one `user` may see".

    Takes the company-id *column* rather than assuming `Company.id`, so it
    works on queries that never join `companies` at all — the pending
    approvals queue, for instance, reaches company_id through ContentPlan.
    """
    is_member = (
        select(CompanyMember.id)
        .where(
            CompanyMember.company_id == company_id_column,
            CompanyMember.user_id == user.id,
        )
        .exists()
    )
    # A company holding nothing but unbound email invites is still
    # unclaimed — invites confer no access until they bind.
    has_any_member = (
        select(CompanyMember.id)
        .where(
            CompanyMember.company_id == company_id_column,
            CompanyMember.user_id.is_not(None),
        )
        .exists()
    )
    return or_(is_member, ~has_any_member)


def accessible_company_clause(user: CurrentUser) -> ColumnElement[bool]:
    """`accessible_company_id_clause` for queries selecting `Company` itself."""
    return accessible_company_id_clause(user, Company.id)


async def register_company_owner(
    session: AsyncSession, company_id: uuid.UUID, user: CurrentUser
) -> None:
    """Record `user` as an owner of a newly-created company.

    Creation is the one moment ownership is unambiguous, so it's recorded
    explicitly rather than left to claim-on-first-access. Idempotent: safe
    to call for a company the user already belongs to.
    """
    existing = (
        await session.execute(
            select(CompanyMember).where(
                CompanyMember.company_id == company_id,
                CompanyMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return

    session.add(
        CompanyMember(
            company_id=company_id,
            user_id=user.id,
            user_email=user.email,
            role="owner",
        )
    )


async def ensure_company_access(
    session: AsyncSession, company_id: uuid.UUID, user: CurrentUser
) -> Company:
    """Return the company if `user` may act on it, else raise 404.

    Call this *before* mutating anything in a handler: claiming an
    unclaimed company and binding a pending invite both commit, and a
    handler's own half-finished changes shouldn't ride along on that
    commit.
    """
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)

    members = (
        (
            await session.execute(
                select(CompanyMember).where(CompanyMember.company_id == company_id)
            )
        )
        .scalars()
        .all()
    )

    # Already a member — the overwhelmingly common path, and it writes
    # nothing.
    if any(member.user_id == user.id for member in members):
        return company

    # A pending invite addressed to this user's email resolves into real
    # membership now. Email comparison is case-insensitive because the
    # inviter typed the address by hand.
    if user.email:
        wanted = user.email.strip().lower()
        for member in members:
            if member.user_id is None and (member.invited_email or "").strip().lower() == wanted:
                member.user_id = user.id
                member.user_email = user.email
                # Cleared so re-inviting the same address later doesn't
                # collide with uq_company_members_company_email.
                member.invited_email = None
                await session.commit()
                return company

    # Unclaimed (pre-ownership data) — first signed-in visitor owns it.
    if not any(member.user_id is not None for member in members):
        session.add(
            CompanyMember(
                company_id=company_id,
                user_id=user.id,
                user_email=user.email,
                role="owner",
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            # Lost a race with a concurrent claim by this same user (e.g.
            # two in-flight requests from one browser). Rolling back and
            # returning is correct — the membership row exists either way.
            await session.rollback()
        return company

    raise HTTPException(status_code=404, detail=_NOT_FOUND)
