"""Company Analyzer routes: list companies, kick off onboarding for a URL,
inspect the extracted profile + onboarding status.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.company_analyzer.graph import run_onboarding
from app.db.models import Company
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
    url = str(payload.url)

    existing = (await session.execute(select(Company).where(Company.url == url))).scalar_one_or_none()
    if existing is not None:
        # Re-onboard: reset to pending and re-run the graph. Existing
        # documents will accumulate; that's fine for now since search
        # will pick the most similar chunks anyway.
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
