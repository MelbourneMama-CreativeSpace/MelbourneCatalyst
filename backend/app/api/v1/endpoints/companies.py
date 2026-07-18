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

router = APIRouter()


@router.post("/", response_model=CompanyCreatedResponse, status_code=202)
async def create_company(
    payload: CompanyCreateRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
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

    existing = (await session.execute(select(Company).where(Company.url == url))).scalar_one_or_none()
    if existing is not None:
        # Re-onboard: wipe the previous run's Documents before resetting to
        # pending. Without this, search results accumulate stale/duplicate
        # chunks across repeated onboardings of the same company.
        await session.execute(delete(Document).where(Document.company_id == existing.id))
        existing.status = "pending"
        existing.status_error = None
        await session.commit()
        background_tasks.add_task(run_onboarding, existing.id, url)
        return CompanyCreatedResponse(id=existing.id, url=url, status=existing.status)

    company = Company(id=uuid.uuid4(), url=url, status="pending")
    session.add(company)
    await session.commit()

    background_tasks.add_task(run_onboarding, company.id, url)
    return CompanyCreatedResponse(id=company.id, url=url, status=company.status)


@router.get("/", response_model=CompanyListResponse)
async def list_companies(session: AsyncSession = Depends(get_session)) -> CompanyListResponse:
    total = (await session.execute(select(func.count()).select_from(Company))).scalar_one()
    rows = (
        await session.execute(select(Company).order_by(Company.updated_at.desc()))
    ).scalars().all()
    return CompanyListResponse(
        items=[CompanyOut.model_validate(row) for row in rows], total=total
    )


@router.get("/{company_id}", response_model=CompanyOut)
async def get_company(
    company_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> CompanyOut:
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyOut.model_validate(company)
