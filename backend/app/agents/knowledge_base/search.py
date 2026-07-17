"""Semantic search over the shared Knowledge Base.

Uses pgvector's cosine-distance operator (`<=>`) against the IVFFlat
index on `documents.embedding` (added in migration 0002). SQLite falls
back to storing embeddings as JSON, so semantic search is Postgres-only —
the API surfaces this as an empty result on non-Postgres backends rather
than crashing.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.knowledge_base.embeddings import embed_query
from app.agents.knowledge_base.schemas import SearchHit
from app.db.models import Document

logger = logging.getLogger(__name__)


async def similarity_search(
    session: AsyncSession,
    query: str,
    *,
    company_id: uuid.UUID | None = None,
    k: int = 5,
) -> list[SearchHit]:
    """Rank the top-k most similar Document chunks to `query`. Empty list on
    unsupported backends (SQLite) or missing embedding key."""
    if session.bind is None or session.bind.dialect.name != "postgresql":
        logger.warning("similarity_search called on non-Postgres backend; returning []")
        return []

    query_embedding = await embed_query(query)
    if query_embedding is None:
        return []

    distance = Document.embedding.cosine_distance(query_embedding)
    stmt = select(Document, distance.label("distance")).where(Document.embedding.is_not(None))
    if company_id is not None:
        stmt = stmt.where(Document.company_id == company_id)
    stmt = stmt.order_by(distance).limit(k)

    rows = (await session.execute(stmt)).all()
    return [
        SearchHit(
            document_id=str(doc.id),
            source_type=doc.source_type,
            source_url=doc.source_url,
            content=doc.content,
            # pgvector cosine_distance ranges [0, 2]; convert to [0, 1]
            # cosine similarity so the API returns a monotone-with-relevance
            # score that's easy for callers to threshold on.
            similarity=1.0 - (dist / 2.0),
            raw_metadata=doc.raw_metadata,
        )
        for doc, dist in rows
    ]
