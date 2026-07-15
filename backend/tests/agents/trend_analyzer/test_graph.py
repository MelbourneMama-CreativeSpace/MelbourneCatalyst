"""Tests for the LangGraph Trend Discovery pipeline: node behavior in
isolation, plus one end-to-end run through a graph built with stub
collectors (never touches the network or the Anthropic API).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.agents.trend_analyzer import graph as graph_module
from app.agents.trend_analyzer.schemas import EnrichedTrendItem, RawTrendItem, TrendSource
from app.db.models import Trend


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

    update = await graph_module._merge_and_dedupe_node({"raw_items": raw_items})

    new_urls = {item.url for item in update["new_items"]}
    assert new_urls == {"https://reddit.com/dupe", "https://example.com/new"}
    assert len(update["new_items"]) == 2


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
    assert final_state["run_summary"]["rss"].error == "down"

    async with test_session_factory() as session:
        rows = (await session.execute(select(Trend))).scalars().all()
    assert len(rows) == 1
