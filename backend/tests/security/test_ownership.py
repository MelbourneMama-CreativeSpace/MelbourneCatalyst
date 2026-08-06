"""Per-company authorization: `app/security/ownership.py`.

Two distinct users throughout — the whole point of this module is that
user B cannot reach user A's data, which a single-user test can't
demonstrate. Every other test file in this suite stubs one fixed user, so
this is the only place the two-tenant case is exercised.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select

from app.db.models import Company, CompanyMember
from app.security.auth import CurrentUser
from app.security.ownership import (
    accessible_company_clause,
    ensure_company_access,
    register_company_owner,
)

USER_A = CurrentUser(id="user-a", email="a@example.com")
USER_B = CurrentUser(id="user-b", email="b@example.com")


@pytest_asyncio.fixture
async def company_id(db_session):
    cid = uuid.uuid4()
    db_session.add(Company(id=cid, url="https://a.example.com", status="complete"))
    await db_session.commit()
    return cid


async def _members(session, company_id) -> list[CompanyMember]:
    return list(
        (
            await session.execute(
                select(CompanyMember).where(CompanyMember.company_id == company_id)
            )
        )
        .scalars()
        .all()
    )


async def test_unknown_company_is_404(db_session):
    with pytest.raises(HTTPException) as exc:
        await ensure_company_access(db_session, uuid.uuid4(), USER_A)
    assert exc.value.status_code == 404


async def test_first_user_to_access_an_unclaimed_company_becomes_its_owner(
    db_session, company_id
):
    """The transition rule for companies created before ownership existed:
    there was no user to attribute them to, so the first one through the
    door claims it."""
    assert await _members(db_session, company_id) == []

    company = await ensure_company_access(db_session, company_id, USER_A)
    assert company.id == company_id

    members = await _members(db_session, company_id)
    assert len(members) == 1
    assert members[0].user_id == USER_A.id
    assert members[0].user_email == USER_A.email
    assert members[0].role == "owner"


async def test_a_second_user_is_404d_once_the_company_is_claimed(db_session, company_id):
    await ensure_company_access(db_session, company_id, USER_A)

    with pytest.raises(HTTPException) as exc:
        await ensure_company_access(db_session, company_id, USER_B)
    assert exc.value.status_code == 404
    # Not 403: a 403 would confirm the id exists, turning an unguessable
    # UUID into an oracle for enumerating other tenants' companies.
    assert exc.value.detail == "Company not found"

    # And the refusal didn't quietly add them.
    assert [m.user_id for m in await _members(db_session, company_id)] == [USER_A.id]


async def test_repeat_access_by_the_owner_creates_no_extra_rows(db_session, company_id):
    for _ in range(3):
        await ensure_company_access(db_session, company_id, USER_A)
    assert len(await _members(db_session, company_id)) == 1


async def test_register_company_owner_is_idempotent(db_session, company_id):
    await register_company_owner(db_session, company_id, USER_A)
    await register_company_owner(db_session, company_id, USER_A)
    await db_session.commit()
    assert len(await _members(db_session, company_id)) == 1


async def test_a_pending_invite_grants_nothing_until_it_binds(db_session, company_id):
    await register_company_owner(db_session, company_id, USER_A)
    db_session.add(
        CompanyMember(company_id=company_id, invited_email="someone@example.com", role="member")
    )
    await db_session.commit()

    # An unrelated user is still refused even though an invite row exists.
    with pytest.raises(HTTPException) as exc:
        await ensure_company_access(db_session, company_id, USER_B)
    assert exc.value.status_code == 404


async def test_an_invite_binds_to_the_matching_user_on_first_access(db_session, company_id):
    await register_company_owner(db_session, company_id, USER_A)
    db_session.add(
        CompanyMember(company_id=company_id, invited_email=USER_B.email, role="member")
    )
    await db_session.commit()

    company = await ensure_company_access(db_session, company_id, USER_B)
    assert company.id == company_id

    bound = [m for m in await _members(db_session, company_id) if m.user_id == USER_B.id]
    assert len(bound) == 1
    assert bound[0].role == "member"
    assert bound[0].user_email == USER_B.email
    # Cleared so re-inviting the same address later can't collide with
    # uq_company_members_company_email.
    assert bound[0].invited_email is None


async def test_invite_email_matching_is_case_insensitive(db_session, company_id):
    await register_company_owner(db_session, company_id, USER_A)
    db_session.add(
        CompanyMember(company_id=company_id, invited_email="B@Example.COM", role="member")
    )
    await db_session.commit()

    company = await ensure_company_access(db_session, company_id, USER_B)
    assert company.id == company_id


async def test_a_company_with_only_an_unbound_invite_is_still_unclaimed(db_session, company_id):
    """An invite is not a member. A company holding nothing but invites has
    no owner yet, so claim-on-first-access still applies."""
    db_session.add(
        CompanyMember(company_id=company_id, invited_email="nobody@example.com", role="member")
    )
    await db_session.commit()

    await ensure_company_access(db_session, company_id, USER_B)
    assert USER_B.id in {m.user_id for m in await _members(db_session, company_id)}


async def test_accessible_clause_matches_ensure_company_access(db_session):
    """The list-filtering clause and the single-row check must agree —
    otherwise a company could be listed but not openable, or vice versa."""
    owned, other, unclaimed = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    for cid, url in ((owned, "a"), (other, "b"), (unclaimed, "c")):
        db_session.add(Company(id=cid, url=f"https://{url}.example.com", status="complete"))
    db_session.add(CompanyMember(company_id=owned, user_id=USER_A.id, role="owner"))
    db_session.add(CompanyMember(company_id=other, user_id=USER_B.id, role="owner"))
    await db_session.commit()

    visible = {
        row.id
        for row in (
            await db_session.execute(select(Company).where(accessible_company_clause(USER_A)))
        )
        .scalars()
        .all()
    }
    assert visible == {owned, unclaimed}

    assert (await ensure_company_access(db_session, owned, USER_A)).id == owned
    with pytest.raises(HTTPException):
        await ensure_company_access(db_session, other, USER_A)
