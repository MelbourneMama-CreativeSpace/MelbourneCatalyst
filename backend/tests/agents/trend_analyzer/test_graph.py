"""Tests for the LangGraph Trend Discovery pipeline: node behavior in
isolation, plus one end-to-end run through a graph built with stub
collectors (never touches the network or the Anthropic API).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.agents.trend_analyzer import graph as graph_module
from app.agents.trend_analyzer.schemas import EnrichedTrendItem, RawTrendItem, SourceResult, TrendSource
from app.db.models import Company, CompanyTrendRelevance, Trend


def _item(source: TrendSource, title: str, url: str) -> RawTrendItem:
    return RawTrendItem(source=source, title=title, url=url, discovered_at=datetime.now(timezone.utc))


class _StubCollector:
    def __init__(self, items: list[RawTrendItem] | None = None, error: Exception | None = None):
        self._items = items or []
        self._error = error

    async def collect(self) -> list[RawTrendItem]:
        if self._error:
            raise self._error
        return self._items


async def _fake_enrich_items(items: list[RawTrendItem]) -> list[EnrichedTrendItem]:
    return [EnrichedTrendItem(item=item, category="marketing", insight="stub insight") for item in items]


async def test_collector_node_records_success():
    node = graph_module._make_collector_node(
        TrendSource.REDDIT, _StubCollector(items=[_item(TrendSource.REDDIT, "A", "https://x/a")])
    )

    update = await node({})

    assert len(update["raw_items"]) == 1
    assert update["run_summary"]["reddit"].item_count == 1
    assert update["run_summary"]["reddit"].error is None


async def test_collector_node_isolates_a_failing_source():
    node = graph_module._make_collector_node(TrendSource.REDDIT, _StubCollector(error=RuntimeError("source is down")))

    update = await node({})

    assert update["raw_items"] == []
    assert "source is down" in update["run_summary"]["reddit"].error


async def test_merge_and_dedupe_drops_within_batch_and_already_persisted_duplicates(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    async with test_session_factory() as session:
        session.add(
            Trend(
                id=uuid.uuid4(),
                source=TrendSource.REDDIT.value,
                title="Already known",
                url="https://reddit.com/known",
                raw_metadata={},
                discovered_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()

    raw_items = [
        _item(TrendSource.REDDIT, "Already known", "https://reddit.com/known"),  # already in DB
        _item(TrendSource.REDDIT, "Duplicate in batch", "https://reddit.com/dupe"),
        _item(TrendSource.REDDIT, "Duplicate in batch", "https://reddit.com/dupe"),  # dupe within batch
        _item(TrendSource.RSS, "Genuinely new", "https://example.com/new"),
    ]
    # As it would actually arrive from the fan-in: one SourceResult per
    # source, item_count set by the collector nodes, new_item_count not yet
    # filled in (that's this node's job).
    run_summary = {
        "reddit": SourceResult(source=TrendSource.REDDIT, item_count=3),
        "rss": SourceResult(source=TrendSource.RSS, item_count=1),
    }

    update = await graph_module._merge_and_dedupe_node(
        {"raw_items": raw_items, "run_summary": run_summary}
    )

    new_urls = {item.url for item in update["new_items"]}
    assert new_urls == {"https://reddit.com/dupe", "https://example.com/new"}
    assert len(update["new_items"]) == 2

    # Per-source new_item_count reflects post-dedup contributions, not raw
    # collected counts: reddit collected 3 but only 1 was genuinely new.
    assert update["run_summary"]["reddit"].new_item_count == 1
    assert update["run_summary"]["reddit"].item_count == 3  # unchanged
    assert update["run_summary"]["rss"].new_item_count == 1


async def test_persist_node_upserts_without_duplicating_on_conflict(monkeypatch, test_session_factory):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    enriched = [
        EnrichedTrendItem(
            item=_item(TrendSource.RSS, "Persisted item", "https://example.com/persist"),
            category="marketing",
            insight="Worth watching",
        )
    ]

    await graph_module._persist_node({"enriched_items": enriched})
    await graph_module._persist_node({"enriched_items": enriched})  # re-run: must not duplicate

    async with test_session_factory() as session:
        rows = (
            await session.execute(select(Trend).where(Trend.url == "https://example.com/persist"))
        ).scalars().all()

    assert len(rows) == 1
    assert rows[0].category == "marketing"


async def test_run_collection_end_to_end_with_stub_collectors(monkeypatch, test_session_factory):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "enrich_items", _fake_enrich_items)

    stub_graph = graph_module._build_graph(
        collectors={
            "collect_stub_a": (
                TrendSource.REDDIT,
                _StubCollector(items=[_item(TrendSource.REDDIT, "A", "https://x/a")]),
            ),
            "collect_stub_b": (TrendSource.RSS, _StubCollector(error=RuntimeError("down"))),
        }
    )

    final_state = await stub_graph.ainvoke(
        {"raw_items": [], "run_summary": {}, "new_items": [], "enriched_items": []}
    )

    assert len(final_state["enriched_items"]) == 1
    assert final_state["run_summary"]["reddit"].item_count == 1
    assert final_state["run_summary"]["reddit"].new_item_count == 1
    assert final_state["run_summary"]["rss"].error == "down"

    async with test_session_factory() as session:
        rows = (await session.execute(select(Trend))).scalars().all()
    assert len(rows) == 1


async def test_score_relevance_node_skips_when_no_company_exists(monkeypatch, test_session_factory):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    enriched = [
        graph_module.EnrichedTrendItem(
            item=_item(TrendSource.RSS, "AI news", "https://example.com/ai"),
            category="technology",
            insight="matters",
        )
    ]

    update = await graph_module._score_relevance_node({"enriched_items": enriched})

    # No company → return enriched_items untouched, relevance_score stays None
    assert update["enriched_items"][0].relevance_score is None


async def test_score_relevance_node_scores_against_company_keywords(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    async with test_session_factory() as session:
        session.add(
            Company(
                id=uuid.uuid4(),
                url="https://example.com",
                status="complete",
                niche_keywords=["marketing automation", "content strategy"],
            )
        )
        await session.commit()

    async def _fake_embed(texts):
        # Return unit vectors where the first component encodes which "topic"
        # each text belongs to. Trend matches keyword[0] more than keyword[1].
        # Keywords: index 0, 1 → embeddings shaped [1, 0], [0, 1]
        # Trend title: index 2 → embedding [1, 0] (matches keyword[0])
        base_dim = 1024
        result = []
        for i, _ in enumerate(texts):
            vec = [0.0] * base_dim
            if i == 0:
                vec[0] = 1.0
            elif i == 1:
                vec[1] = 1.0
            else:
                vec[0] = 1.0
            result.append(vec)
        return result

    monkeypatch.setattr(graph_module, "embed_documents", _fake_embed)

    enriched = [
        graph_module.EnrichedTrendItem(
            item=_item(TrendSource.RSS, "AI marketing tools", "https://example.com/ai"),
            category="marketing",
            insight="matters",
        )
    ]

    update = await graph_module._score_relevance_node({"enriched_items": enriched})

    scored = update["enriched_items"][0]
    assert scored.relevance_score is not None
    # Cosine sim with [1,0] is 1.0, normalized to (1+1)/2 = 1.0
    assert scored.relevance_score == 1.0


async def _fake_embed_matching_keywords(texts: list[str]) -> list[list[float]]:
    # Every text embeds to the same unit vector, so every (company,
    # trend) pair gets cosine similarity 1.0 → normalized relevance 1.0.
    # Enough to prove rows get written; the actual scoring math is
    # already covered by test_score_relevance_node_scores_against_company_keywords.
    return [[1.0, 0.0] for _ in texts]


async def test_persist_node_writes_per_company_relevance_for_every_complete_company(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "embed_documents", _fake_embed_matching_keywords)

    company_a = uuid.uuid4()
    company_b = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Company(
                id=company_a,
                url="https://a.example.com",
                status="complete",
                niche_keywords=["marketing"],
            )
        )
        session.add(
            Company(
                id=company_b,
                url="https://b.example.com",
                status="complete",
                niche_keywords=["parenting"],
            )
        )
        await session.commit()

    enriched = [
        EnrichedTrendItem(
            item=_item(TrendSource.RSS, "Per-company scoring test", "https://example.com/multi"),
            category="marketing",
            insight="matters",
        )
    ]

    await graph_module._persist_node({"enriched_items": enriched})

    async with test_session_factory() as session:
        trend = (
            await session.execute(select(Trend).where(Trend.url == "https://example.com/multi"))
        ).scalar_one()
        rows = (
            await session.execute(
                select(CompanyTrendRelevance).where(CompanyTrendRelevance.trend_id == trend.id)
            )
        ).scalars().all()

    scores_by_company = {row.company_id: row.relevance_score for row in rows}
    assert scores_by_company == {company_a: 1.0, company_b: 1.0}


async def test_persist_node_skips_companies_without_niche_keywords(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "embed_documents", _fake_embed_matching_keywords)

    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(
            Company(id=company_id, url="https://no-keywords.example.com", status="complete")
        )
        await session.commit()

    enriched = [
        EnrichedTrendItem(
            item=_item(TrendSource.RSS, "No keywords company", "https://example.com/no-kw"),
            category="marketing",
            insight="matters",
        )
    ]

    await graph_module._persist_node({"enriched_items": enriched})

    async with test_session_factory() as session:
        rows = (await session.execute(select(CompanyTrendRelevance))).scalars().all()
    assert rows == []


async def test_persist_node_writes_no_relevance_rows_when_embeddings_unconfigured(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    async def _no_embeddings(texts: list[str]) -> list[None]:
        return [None] * len(texts)

    monkeypatch.setattr(graph_module, "embed_documents", _no_embeddings)

    async with test_session_factory() as session:
        session.add(
            Company(
                id=uuid.uuid4(),
                url="https://example.com",
                status="complete",
                niche_keywords=["marketing"],
            )
        )
        await session.commit()

    enriched = [
        EnrichedTrendItem(
            item=_item(TrendSource.RSS, "No embeddings", "https://example.com/no-embed"),
            category="marketing",
            insight="matters",
        )
    ]

    # Must not raise even though embeddings are entirely unavailable.
    await graph_module._persist_node({"enriched_items": enriched})

    async with test_session_factory() as session:
        rows = (await session.execute(select(CompanyTrendRelevance))).scalars().all()
    assert rows == []
