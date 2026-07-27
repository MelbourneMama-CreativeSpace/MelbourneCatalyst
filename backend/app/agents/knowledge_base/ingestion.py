"""Shared ingestion primitive for every Knowledge Base source (manual entry,
file upload, blog indexing, scheduled re-indexing — website *onboarding*
has its own pipeline in `company_analyzer/graph.py` since it's bundled
with profile extraction, though the scheduled re-index job below reuses
this module for its ongoing re-scrapes).

Every source builds a `RawDocument` and calls `ingest_raw_document`, which
chunks, embeds, and persists it. Re-running ingestion for the same
`source_url` replaces the old rows rather than accumulating duplicates —
the same dedup shape already used for company re-onboarding.
"""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import delete, select
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


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def ingest_raw_document_if_changed(
    session: AsyncSession, company_id: uuid.UUID, raw: RawDocument
) -> tuple[int, bool]:
    """Same as `ingest_raw_document`, but skips entirely — no embedding
    call, no delete-then-reinsert — when the content for this `source_url`
    is byte-identical to what's already stored, tagged via a
    `content_hash` in `raw_metadata`. Built for the scheduled re-index job,
    which re-scrapes every complete company's site on an interval and
    would otherwise re-embed every page every time even when nothing
    changed. A source with no prior recorded hash (e.g. it was ingested
    before this function existed) is treated as changed — re-embedding
    once is cheaper than silently trusting an absent hash.

    Returns `(chunks_persisted, skipped)`. Does not commit — same
    transaction contract as `ingest_raw_document`."""
    new_hash = _content_hash(raw.content)

    existing_metadata = (
        await session.execute(
            select(Document.raw_metadata)
            .where(Document.company_id == company_id, Document.source_url == raw.source_url)
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing_metadata is not None and existing_metadata.get("content_hash") == new_hash:
        return 0, True

    raw.raw_metadata = {**raw.raw_metadata, "content_hash": new_hash}
    count = await ingest_raw_document(session, company_id, raw)
    return count, False
