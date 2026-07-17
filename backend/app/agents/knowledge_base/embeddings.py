"""Voyage AI embeddings wrapper.

Uses the official `voyageai` SDK's `AsyncClient` so embedding calls
don't block the event loop. Batches inputs (Voyage caps batch size at
128 for voyage-3-lite) and falls back to `None`s on API failure so a
transient error doesn't lose the whole onboarding run — the downstream
persist step just skips embedding-less chunks.
"""

from __future__ import annotations

import logging

import voyageai

from app.config import settings

logger = logging.getLogger(__name__)

# voyage-3-lite: 32k context, 1024-dim default (matches EMBEDDING_DIM in models).
_BATCH_SIZE = 128


def _client() -> voyageai.AsyncClient:
    return voyageai.AsyncClient(api_key=settings.VOYAGE_API_KEY)


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def embed_documents(texts: list[str]) -> list[list[float] | None]:
    """Embed a list of documents. Returns one embedding (or None on failure) per input."""
    if not texts:
        return []
    if not settings.VOYAGE_API_KEY:
        logger.warning("VOYAGE_API_KEY not configured; skipping embedding")
        return [None] * len(texts)

    client = _client()
    embeddings: list[list[float] | None] = []
    for batch in _chunks(texts, _BATCH_SIZE):
        try:
            response = await client.embed(
                texts=batch, model=settings.VOYAGE_MODEL, input_type="document"
            )
            embeddings.extend(response.embeddings)
        except Exception:
            logger.exception("Voyage embed batch of %d failed", len(batch))
            embeddings.extend([None] * len(batch))
    return embeddings


async def embed_query(text: str) -> list[float] | None:
    """Embed a single search query. Returns None on failure."""
    if not settings.VOYAGE_API_KEY:
        logger.warning("VOYAGE_API_KEY not configured; skipping query embedding")
        return None
    try:
        response = await _client().embed(
            texts=[text], model=settings.VOYAGE_MODEL, input_type="query"
        )
        return response.embeddings[0]
    except Exception:
        logger.exception("Voyage query embed failed")
        return None
