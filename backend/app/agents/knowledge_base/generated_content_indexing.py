"""Indexes the app's own generated content (approved ContentItems,
Strategies) into the same Document/pgvector store that otherwise only
holds externally-ingested material (scraped sites, uploads, blog posts).
Closes the gap where neither plain KB search nor the chat agent's
`search_knowledge_base` tool could find a company's own approved
captions or strategy — everything downstream (search, chat) inherits
this automatically once content lands in `Document`, no changes needed
there.

Triggered on approval, not on every generation — indexing a rejected or
still-pending draft would pollute search results with content that may
never represent the brand's actual voice.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.knowledge_base.ingestion import ingest_raw_document
from app.agents.knowledge_base.schemas import RawDocument


async def index_on_approval(
    session: AsyncSession, company_id: uuid.UUID, source_type: str, source_url: str, content: str
) -> None:
    """Best-effort — mirrors `ingest_raw_document`'s own contract (no-ops
    on empty content, degrades gracefully with no `VOYAGE_API_KEY` since
    `embed_documents` already handles that). Does not commit; the caller
    controls the transaction, same as `ingest_raw_document` itself."""
    if not content or not content.strip():
        return
    await ingest_raw_document(
        session,
        company_id,
        RawDocument(source_type=source_type, source_url=source_url, content=content),
    )
