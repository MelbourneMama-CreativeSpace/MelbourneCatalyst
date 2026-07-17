"""Tests for the Knowledge Base chunker."""

from __future__ import annotations

from app.agents.knowledge_base.chunker import chunk_text


def test_chunk_text_empty_input_returns_empty_list():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_short_input_returns_single_chunk():
    result = chunk_text("A short paragraph.")
    assert result == ["A short paragraph."]


def test_chunk_text_long_input_splits_into_multiple_chunks_with_overlap():
    long_text = "sentence one. " * 300
    result = chunk_text(long_text, chunk_size=200, chunk_overlap=20)

    assert len(result) > 1
    assert all(len(c) <= 200 for c in result)
