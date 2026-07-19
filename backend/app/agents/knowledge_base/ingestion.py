"""Shared ingestion primitive for every Knowledge Base source (manual entry,
file upload, blog indexing — website onboarding has its own pipeline in
`company_analyzer/graph.py` since it's bundled with profile extraction).

Every source builds a `RawDocument` and calls `ingest_raw_document`, which
chunks, embeds, and persists it. Re-running ingestion for the same
`source_url` replaces the old rows rather than accumulating duplicates —
the same dedup shape already used for company re-onboarding.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.knowledge_base.chunker import chunk_text
from app.agents.knowledge_base.embeddings import embed_documents
from app.agents.knowledge_base.schemas import RawDocument
from app.db.models import Document


async def ingest_raw_document(
    session: AsyncSession, company_id: uuid.UUID, raw: RawDocument
) -> int:
    """Chunk, embed, and persist one `RawDocument`. Returns the number of
    chunks persisted (0 if the content was empty/whitespace-only). Does not
    commit — the caller controls the transaction so multiple documents can
    be ingested in one commit."""
    chunks = chunk_text(raw.content)
    if not chunks:
        return 0

    embeddings = await embed_documents(chunks)

    await session.execute(
        delete(Document).where(
            Document.company_id == company_id, Document.source_url == raw.source_url
        )
    )
    session.add_all(
        [
            Document(
                id=uuid.uuid4(),
                company_id=company_id,
                source_type=raw.source_type,
                source_url=raw.source_url,
                chunk_index=i,
                content=chunk,
                embedding=embedding,
                raw_metadata=raw.raw_metadata,
            )
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
    )
    return len(chunks)
