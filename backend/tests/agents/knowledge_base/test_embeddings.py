"""Tests for the Voyage embeddings wrapper."""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.knowledge_base import embeddings


async def test_embed_documents_empty_input():
    assert await embeddings.embed_documents([]) == []


async def test_embed_documents_no_api_key_returns_none_per_input(monkeypatch):
    monkeypatch.setattr(embeddings.settings, "VOYAGE_API_KEY", "")

    result = await embeddings.embed_documents(["a", "b", "c"])

    assert result == [None, None, None]


async def test_embed_documents_batches_and_returns_embeddings(monkeypatch):
    monkeypatch.setattr(embeddings.settings, "VOYAGE_API_KEY", "test-key")

    call_count = {"n": 0}

    class _FakeClient:
        async def embed(self, texts, model, input_type):
            call_count["n"] += 1
            return SimpleNamespace(embeddings=[[0.1] * 1024 for _ in texts])

    monkeypatch.setattr(embeddings, "_client", lambda: _FakeClient())
    # Force small batches to verify batching
    monkeypatch.setattr(embeddings, "_BATCH_SIZE", 2)

    result = await embeddings.embed_documents(["a", "b", "c", "d", "e"])

    assert len(result) == 5
    assert call_count["n"] == 3  # ceil(5/2)
    assert all(len(e) == 1024 for e in result)


async def test_embed_documents_falls_back_on_batch_failure(monkeypatch):
    monkeypatch.setattr(embeddings.settings, "VOYAGE_API_KEY", "test-key")

    class _FailingClient:
        async def embed(self, texts, model, input_type):
            raise RuntimeError("Voyage down")

    monkeypatch.setattr(embeddings, "_client", lambda: _FailingClient())

    result = await embeddings.embed_documents(["a", "b"])

    assert result == [None, None]


async def test_embed_query_returns_none_without_api_key(monkeypatch):
    monkeypatch.setattr(embeddings.settings, "VOYAGE_API_KEY", "")

    assert await embeddings.embed_query("hello") is None


async def test_embed_query_returns_embedding_on_success(monkeypatch):
    monkeypatch.setattr(embeddings.settings, "VOYAGE_API_KEY", "test-key")

    class _FakeClient:
        async def embed(self, texts, model, input_type):
            return SimpleNamespace(embeddings=[[0.5] * 1024])

    monkeypatch.setattr(embeddings, "_client", lambda: _FakeClient())

    result = await embeddings.embed_query("hello")

    assert result is not None
    assert len(result) == 1024
