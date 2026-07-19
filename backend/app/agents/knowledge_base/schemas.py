"""Internal data shapes for the Knowledge Base."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RawDocument:
    """A source document before chunking — one page scrape, one uploaded PDF, etc."""

    source_type: str
    source_url: str
    content: str
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EmbeddedChunk:
    """A single chunk + its Voyage embedding, ready to persist as a Document row."""

    source_type: str
    source_url: str
    chunk_index: int
    content: str
    embedding: list[float] | None
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SearchHit:
    """A ranked semantic-search result, returned by search.similarity_search."""

    document_id: str
    source_type: str
    source_url: str
    content: str
    similarity: float
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GeneratedAudit:
    """Claude's structured output for `generate_audit`."""

    coverage_summary: str | None = None
    identified_gaps: str | None = None
    recommendations: str | None = None
