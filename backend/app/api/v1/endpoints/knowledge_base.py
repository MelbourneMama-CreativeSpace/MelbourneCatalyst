"""Knowledge Base routes: semantic search over ingested company documents,
document CRUD + ingestion sources (manual entry, file upload, blog
indexing), plus the Knowledge Manager's freshness indicator and audit
reports."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.knowledge_base.audit_graph import run_knowledge_audit_generation
from app.agents.knowledge_base.blog_indexer import index_blog_feeds
from app.agents.knowledge_base.file_extraction import UnsupportedFileTypeError, extract_text_from_upload
from app.agents.knowledge_base.ingestion import ingest_raw_document
from app.agents.knowledge_base.schemas import RawDocument
from app.agents.knowledge_base.search import similarity_search
from app.config import settings
from app.db.models import Company, Document, KnowledgeAuditReport
from app.db.session import get_session
from app.models.knowledge_base import (
    BlogIndexRequest,
    DocumentDetailOut,
    DocumentListResponse,
    DocumentOut,
    IngestionResultOut,
    KnowledgeAuditReportCreateRequest,
    KnowledgeAuditReportListResponse,
    KnowledgeAuditReportOut,
    KnowledgeFreshnessOut,
    ManualDocumentCreateRequest,
    SearchHitOut,
    SearchResponse,
)
from app.security.auth import CurrentUser, get_current_user
from app.security.ownership import get_owned_company, owned_company_ids

router = APIRouter(dependencies=[Depends(get_current_user)])


async def _get_company_or_404(
    session: AsyncSession, company_id: uuid.UUID, current_user: CurrentUser
) -> Company:
    return await get_owned_company(session, company_id, current_user)


async def _get_ready_company_or_error(
    session: AsyncSession, company_id: uuid.UUID, current_user: CurrentUser
) -> Company:
    """Same guard as content_management.py's / trends.py's."""
    company = await _get_company_or_404(session, company_id, current_user)
    if company.status != "complete":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Company profile is not ready (status: {company.status}). "
                "Onboarding must complete successfully before generating an audit report."
            ),
        )
    return company


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1),
    company_id: uuid.UUID | None = None,
    k: int = Query(default=5, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> SearchResponse:
    if company_id is not None:
        await get_owned_company(session, company_id, current_user)
        hits = await similarity_search(session, q, company_id=company_id, k=k)
    else:
        owned_ids = await owned_company_ids(session, current_user)
        hits = await similarity_search(session, q, company_ids=owned_ids, k=k)
    return SearchResponse(
        query=q,
        hits=[
            SearchHitOut(
                document_id=hit.document_id,
                source_type=hit.source_type,
                source_url=hit.source_url,
                content=hit.content,
                similarity=hit.similarity,
            )
            for hit in hits
        ],
    )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    company_id: uuid.UUID,
    source_type: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> DocumentListResponse:
    """Lightweight preview list — no company-readiness guard, since
    browsing/managing the KB should work regardless of onboarding status."""
    await get_owned_company(session, company_id, current_user)
    effective_limit = limit or settings.KB_DOCUMENT_LIST_DEFAULT_LIMIT
    stmt = select(Document).where(Document.company_id == company_id).order_by(Document.created_at.desc())
    count_stmt = select(func.count()).select_from(Document).where(Document.company_id == company_id)
    if source_type is not None:
        stmt = stmt.where(Document.source_type == source_type)
        count_stmt = count_stmt.where(Document.source_type == source_type)
    stmt = stmt.limit(effective_limit).offset(offset)

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(stmt)).scalars().all()
    return DocumentListResponse(
        items=[
            DocumentOut(
                id=row.id,
                source_type=row.source_type,
                source_url=row.source_url,
                content_preview=row.content[:240],
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
    )


@router.post("/documents/manual", response_model=IngestionResultOut)
async def create_manual_document(
    payload: ManualDocumentCreateRequest,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> IngestionResultOut:
    await _get_company_or_404(session, payload.company_id, current_user)

    raw = RawDocument(
        source_type="manual",
        source_url=f"manual://{uuid.uuid4()}",
        content=payload.content,
        raw_metadata={"title": payload.title},
    )
    chunks_persisted = await ingest_raw_document(session, payload.company_id, raw)
    await session.commit()
    return IngestionResultOut(sources_processed=1, chunks_persisted=chunks_persisted)


@router.post("/documents/upload", response_model=IngestionResultOut)
async def upload_document(
    company_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> IngestionResultOut:
    await _get_company_or_404(session, company_id, current_user)

    content_bytes = await file.read()
    if len(content_bytes) > settings.KB_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds maximum upload size")

    try:
        text = await asyncio.to_thread(
            extract_text_from_upload, file.filename or "upload", content_bytes
        )
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    raw = RawDocument(
        source_type="doc_upload",
        source_url=f"upload://{file.filename or uuid.uuid4()}",
        content=text,
        raw_metadata={"filename": file.filename},
    )
    chunks_persisted = await ingest_raw_document(session, company_id, raw)
    await session.commit()
    return IngestionResultOut(sources_processed=1, chunks_persisted=chunks_persisted)


@router.post("/documents/blog-index", response_model=IngestionResultOut)
async def index_blog(
    payload: BlogIndexRequest,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> IngestionResultOut:
    await _get_company_or_404(session, payload.company_id, current_user)

    documents = await index_blog_feeds(payload.feed_urls, max_articles=settings.KB_BLOG_MAX_ARTICLES)

    chunks_persisted = 0
    for raw in documents:
        chunks_persisted += await ingest_raw_document(session, payload.company_id, raw)
    await session.commit()
    return IngestionResultOut(sources_processed=len(documents), chunks_persisted=chunks_persisted)


@router.get("/documents/{document_id}", response_model=DocumentDetailOut)
async def get_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> DocumentDetailOut:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    await get_owned_company(session, document.company_id, current_user)
    return DocumentDetailOut.model_validate(document)


@router.delete("/documents/{document_id}", response_model=DocumentDetailOut)
async def delete_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> DocumentDetailOut:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    await get_owned_company(session, document.company_id, current_user)
    deleted = DocumentDetailOut.model_validate(document)
    await session.delete(document)
    await session.commit()
    return deleted


@router.get("/freshness", response_model=KnowledgeFreshnessOut)
async def get_freshness(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> KnowledgeFreshnessOut:
    """Purely derived from `documents` — no Claude call, works regardless
    of onboarding status (a company mid-onboarding legitimately has 0
    documents, which is itself useful information, not an error)."""
    await get_owned_company(session, company_id, current_user)

    row = (
        await session.execute(
            select(func.count(), func.max(Document.created_at)).where(
                Document.company_id == company_id
            )
        )
    ).one()
    document_count, last_ingested_at = row

    staleness_days = None
    if last_ingested_at is not None:
        reference = last_ingested_at
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        staleness_days = (datetime.now(timezone.utc) - reference).days

    return KnowledgeFreshnessOut(
        company_id=company_id,
        document_count=document_count,
        last_ingested_at=last_ingested_at,
        staleness_days=staleness_days,
    )


@router.post("/audit-reports", response_model=KnowledgeAuditReportOut)
async def create_audit_report(
    payload: KnowledgeAuditReportCreateRequest,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> KnowledgeAuditReportOut:
    await _get_ready_company_or_error(session, payload.company_id, current_user)

    report = KnowledgeAuditReport(id=uuid.uuid4(), company_id=payload.company_id, status="pending")
    session.add(report)
    await session.commit()

    await run_knowledge_audit_generation(report.id, payload.company_id)

    refreshed = (
        await session.execute(
            select(KnowledgeAuditReport)
            .execution_options(populate_existing=True)
            .where(KnowledgeAuditReport.id == report.id)
        )
    ).scalar_one()
    return KnowledgeAuditReportOut.model_validate(refreshed)


@router.get("/audit-reports", response_model=KnowledgeAuditReportListResponse)
async def list_audit_reports(
    company_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> KnowledgeAuditReportListResponse:
    if company_id is not None:
        await get_owned_company(session, company_id, current_user)
        owned_ids: list[uuid.UUID] = [company_id]
    else:
        owned_ids = await owned_company_ids(session, current_user)

    stmt = (
        select(KnowledgeAuditReport)
        .where(KnowledgeAuditReport.company_id.in_(owned_ids))
        .order_by(KnowledgeAuditReport.created_at.desc())
    )
    count_stmt = (
        select(func.count())
        .select_from(KnowledgeAuditReport)
        .where(KnowledgeAuditReport.company_id.in_(owned_ids))
    )

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(stmt)).scalars().all()
    return KnowledgeAuditReportListResponse(
        items=[KnowledgeAuditReportOut.model_validate(row) for row in rows], total=total
    )


@router.get("/audit-reports/{report_id}", response_model=KnowledgeAuditReportOut)
async def get_audit_report(
    report_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
) -> KnowledgeAuditReportOut:
    report = await session.get(KnowledgeAuditReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Audit report not found")
    await get_owned_company(session, report.company_id, current_user)
    return KnowledgeAuditReportOut.model_validate(report)
