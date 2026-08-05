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
from app.db.models import Company, Document
from app.db.session import get_session
from app.models.company import (
    CompanyCreatedResponse,
    CompanyCreateRequest,
    CompanyListResponse,
    CompanyOut,
)
from app.security.auth import CurrentUser, get_current_user
from app.security.ownership import get_owned_company

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/", response_model=CompanyCreatedResponse, status_code=202)
async def create_company(
    payload: CompanyCreateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> CompanyCreatedResponse:
    """Start onboarding for a new company URL. Returns the pending row and
    kicks off the LangGraph pipeline in the background — the caller polls
    `GET /companies/{id}` until status becomes 'complete' or 'failed'.
    """
    # Normalize before the dedup lookup and storage so "example.com",
    # "https://example.com", and "https://example.com/" all resolve to the
    # same Company row instead of creating duplicates — Pydantic's HttpUrl
    # doesn't normalize this consistently on its own.
    url = normalize_url(str(payload.url))

    # Dedup is scoped to the caller's own companies — two different users
    # onboarding the same URL each get their own private row, not one
    # shared row (that would leak one user's re-onboard into another's).
    existing = (
        await session.execute(
            select(Company).where(Company.url == url, Company.owner_id == current_user.id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Re-onboard: wipe the previous run's Documents before resetting to
        # pending. Without this, search results accumulate stale/duplicate
        # chunks across repeated onboardings of the same company.
        await session.execute(delete(Document).where(Document.company_id == existing.id))
        existing.status = "pending"
        existing.status_error = None
        if payload.name:
            existing.name = payload.name
        await session.commit()
        background_tasks.add_task(run_onboarding, existing.id, url)
        return CompanyCreatedResponse(id=existing.id, url=url, name=existing.name, status=existing.status)

    company = Company(
        id=uuid.uuid4(), url=url, name=payload.name, status="pending", owner_id=current_user.id
    )
    session.add(company)
    await session.commit()

    background_tasks.add_task(run_onboarding, company.id, url)
    return CompanyCreatedResponse(id=company.id, url=url, name=company.name, status=company.status)


@router.get("/", response_model=CompanyListResponse)
async def list_companies(
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> CompanyListResponse:
    stmt = select(Company).where(Company.owner_id == current_user.id)
    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        await session.execute(stmt.order_by(Company.updated_at.desc()))
    ).scalars().all()
    return CompanyListResponse(
        items=[CompanyOut.model_validate(row) for row in rows], total=total
    )


@router.get("/{company_id}", response_model=CompanyOut)
async def get_company(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> CompanyOut:
    company = await get_owned_company(session, company_id, current_user)
    return CompanyOut.model_validate(company)
