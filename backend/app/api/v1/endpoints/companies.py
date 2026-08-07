"""Company Analyzer routes: list companies, kick off onboarding for a URL,
inspect the extracted profile + onboarding status.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.company_analyzer.graph import run_onboarding
from app.agents.company_analyzer.scraper import normalize_url
from app.db.models import Company, CompanyMember, Document
from app.db.session import get_session
from app.models.company import (
    CompanyCreatedResponse,
    CompanyCreateRequest,
    CompanyListResponse,
    CompanyMemberInviteRequest,
    CompanyMemberListResponse,
    CompanyMemberOut,
    CompanyOut,
)
from app.security.auth import CurrentUser, get_current_user
from app.security.ownership import (
    accessible_company_clause,
    ensure_company_access,
    register_company_owner,
)

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/", response_model=CompanyCreatedResponse, status_code=202)
async def create_company(
    payload: CompanyCreateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CompanyCreatedResponse:
    """Start onboarding for a new company. Returns the pending row and
    kicks off the LangGraph pipeline in the background — the caller polls
    `GET /companies/{id}` until status becomes 'complete' or 'failed'.

    Takes a website URL, a typed description, or both (the request model
    rejects neither). Only a URL identifies a company well enough to
    de-duplicate against: two businesses can describe themselves
    identically, so a description-only request always creates a new row.
    """
    # Normalize before the dedup lookup and storage so "example.com",
    # "https://example.com", and "https://example.com/" all resolve to the
    # same Company row instead of creating duplicates — Pydantic's HttpUrl
    # doesn't normalize this consistently on its own.
    url = normalize_url(str(payload.url)) if payload.url is not None else None
    description = (payload.description or "").strip() or None

    existing = (
        (await session.execute(select(Company).where(Company.url == url))).scalar_one_or_none()
        if url is not None
        else None
    )
    if existing is not None:
        # Ownership check before the re-onboard, not after: without it this
        # branch is a hijack path — POSTing a URL that already belongs to
        # someone else would wipe their documents and restart their
        # onboarding, no company id needed. 404s (not 403s) for a
        # non-member, same as everywhere else, so this doesn't become a way
        # to test whether a given URL is already onboarded.
        await ensure_company_access(session, existing.id, user)

        # Re-onboard: wipe the previous run's Documents before resetting to
        # pending. Without this, search results accumulate stale/duplicate
        # chunks across repeated onboardings of the same company.
        await session.execute(delete(Document).where(Document.company_id == existing.id))
        existing.status = "pending"
        existing.status_error = None
        # A re-onboard that omits the description keeps the stored one —
        # it's raw human input that extraction never regenerates, so
        # dropping it would silently degrade the profile on every re-run.
        if description is not None:
            existing.description = description
        await session.commit()
        background_tasks.add_task(run_onboarding, existing.id, url, existing.description)
        return CompanyCreatedResponse(
            id=existing.id, url=url, name=existing.name, status=existing.status
        )

    company = Company(id=uuid.uuid4(), url=url, description=description, status="pending")
    session.add(company)
    # Creation is the one moment ownership is unambiguous — recorded here
    # rather than relying on the claim-on-first-access fallback, which
    # exists only for companies that predate ownership.
    await register_company_owner(session, company.id, user)
    await session.commit()

    background_tasks.add_task(run_onboarding, company.id, url, description)
    return CompanyCreatedResponse(id=company.id, url=url, name=company.name, status=company.status)


@router.get("/", response_model=CompanyListResponse)
async def list_companies(
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CompanyListResponse:
    """Only companies this user belongs to (plus any still unclaimed).

    `total` counts the same filtered set — a global count would leak how
    many other tenants exist.
    """
    visible = accessible_company_clause(user)
    total = (
        await session.execute(select(func.count()).select_from(Company).where(visible))
    ).scalar_one()
    rows = (
        await session.execute(
            select(Company).where(visible).order_by(Company.updated_at.desc())
        )
    ).scalars().all()
    return CompanyListResponse(
        items=[CompanyOut.model_validate(row) for row in rows], total=total
    )


@router.get("/{company_id}", response_model=CompanyOut)
async def get_company(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CompanyOut:
    company = await ensure_company_access(session, company_id, user)
    return CompanyOut.model_validate(company)


@router.get("/{company_id}/members", response_model=CompanyMemberListResponse)
async def list_company_members(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CompanyMemberListResponse:
    await ensure_company_access(session, company_id, user)
    rows = (
        (
            await session.execute(
                select(CompanyMember)
                .where(CompanyMember.company_id == company_id)
                .order_by(CompanyMember.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return CompanyMemberListResponse(
        items=[CompanyMemberOut.model_validate(row) for row in rows],
        current_user_id=user.id,
    )


@router.post("/{company_id}/members", response_model=CompanyMemberOut, status_code=201)
async def invite_company_member(
    company_id: uuid.UUID,
    payload: CompanyMemberInviteRequest,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CompanyMemberOut:
    """Invite someone by email.

    The invite is inert until that person signs in — it stores the address
    and nothing else. No email is sent (this app has no delivery channel;
    see KNOWN_ISSUES.md's note on trend alerts for the same gap), so the
    inviter still has to tell them out of band. Binding happens in
    `ensure_company_access` the first time a token carrying that email
    reaches this company.
    """
    await ensure_company_access(session, company_id, user)
    email = payload.email

    existing = (
        await session.execute(
            select(CompanyMember).where(
                CompanyMember.company_id == company_id,
                func.lower(CompanyMember.invited_email) == email,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="That email is already invited")

    already_member = (
        await session.execute(
            select(CompanyMember).where(
                CompanyMember.company_id == company_id,
                func.lower(CompanyMember.user_email) == email,
                CompanyMember.user_id.is_not(None),
            )
        )
    ).scalar_one_or_none()
    if already_member is not None:
        raise HTTPException(status_code=409, detail="That person is already a member")

    member = CompanyMember(company_id=company_id, invited_email=email, role="member")
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return CompanyMemberOut.model_validate(member)


@router.delete("/{company_id}/members/{member_id}", response_model=CompanyMemberOut)
async def remove_company_member(
    company_id: uuid.UUID,
    member_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> CompanyMemberOut:
    await ensure_company_access(session, company_id, user)

    member = await session.get(CompanyMember, member_id)
    if member is None or member.company_id != company_id:
        raise HTTPException(status_code=404, detail="Member not found")

    # Removing the last real member would return the company to "unclaimed"
    # — i.e. visible to every signed-in user again, silently undoing the
    # thing this whole feature exists to do. Refused rather than allowed
    # with a warning.
    remaining = (
        await session.execute(
            select(func.count())
            .select_from(CompanyMember)
            .where(
                CompanyMember.company_id == company_id,
                CompanyMember.user_id.is_not(None),
                CompanyMember.id != member_id,
            )
        )
    ).scalar_one()
    if member.user_id is not None and remaining == 0:
        raise HTTPException(
            status_code=409,
            detail="Cannot remove the last member — the company would become unowned",
        )

    # Serialized before the delete — same shape as this codebase's other
    # DELETE routes (delete_document, delete_media_asset), which return the
    # row they removed rather than an empty 204.
    removed = CompanyMemberOut.model_validate(member)
    await session.delete(member)
    await session.commit()
    return removed
