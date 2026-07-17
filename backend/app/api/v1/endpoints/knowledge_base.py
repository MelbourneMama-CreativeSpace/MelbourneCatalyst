"""Knowledge Base routes: semantic search over ingested company documents."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.knowledge_base.search import similarity_search
from app.db.session import get_session
from app.models.knowledge_base import SearchHitOut, SearchResponse

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1),
    company_id: uuid.UUID | None = None,
    k: int = Query(default=5, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    hits = await similarity_search(session, q, company_id=company_id, k=k)
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
