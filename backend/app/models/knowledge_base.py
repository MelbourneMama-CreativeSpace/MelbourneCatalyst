"""Pydantic response schemas for Knowledge Base search."""

from __future__ import annotations

from pydantic import BaseModel


class SearchHitOut(BaseModel):
    document_id: str
    source_type: str
    source_url: str
    content: str
    similarity: float


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHitOut]
