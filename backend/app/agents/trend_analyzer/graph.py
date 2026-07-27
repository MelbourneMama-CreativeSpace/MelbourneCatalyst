"""LangGraph pipeline for the Trend Discovery run.

    START ─┬─> collect_google_trends ─┐
           ├─> collect_reddit ────────┤
           ├─> collect_rss ───────────┤                                             ┌─> score_relevance ─┐
           ├─> collect_youtube ───────┼─> merge_and_dedupe ─> enrich_with_claude ──┤                     ├─> persist ─> END
           ├─> collect_twitter ───────┤                                             └────────────────────┘
           ├─> collect_instagram ─────┤   (score_relevance is a no-op when no company has been onboarded
           └─> collect_tiktok ────────┘    yet — it just leaves relevance_score NULL on new trends)

Collector nodes fan out from START and run concurrently; LangGraph waits for
all seven before running `merge_and_dedupe` (fan-in). Using a graph instead of
a plain `asyncio.gather` buys two things: LangGraph automatically exports
per-node traces to LangSmith when `LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY`
are set (nothing else to wire up), and `enrich_with_claude` only ever sees
`new_items` — trends already in the DB never reach the LLM node again, which
is what keeps Claude token spend bounded as the trend feed grows.
"""

from __future__ import annotations

import dataclasses
import logging
import operator
import uuid
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import insert, select, tuple_
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.trend_analyzer.collectors.base import Collector
from app.agents.trend_analyzer.collectors.google_trends import GoogleTrendsCollector
from app.agents.trend_analyzer.collectors.instagram import InstagramCollector
from app.agents.trend_analyzer.collectors.reddit import RedditCollector
from app.agents.trend_analyzer.collectors.rss import RSSCollector
from app.agents.trend_analyzer.collectors.tiktok import TikTokCollector
from app.agents.trend_analyzer.collectors.twitter import TwitterCollector
from app.agents.trend_analyzer.collectors.youtube import YouTubeCollector
from app.agents.knowledge_base.embeddings import embed_documents
from app.agents.trend_analyzer.enrichment import enrich_items
from app.agents.trend_analyzer.schemas import (
    EnrichedTrendItem,
    RawTrendItem,
    RunResult,
    SourceResult,
    TrendSource,
)
from app.db.models import Company, CompanyTrendRelevance, Trend
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


def _merge_source_results(
    a: dict[str, SourceResult], b: dict[str, SourceResult]
) -> dict[str, SourceResult]:
    return {**a, **b}


class TrendGraphState(TypedDict):
    raw_items: Annotated[list[RawTrendItem], operator.add]
    run_summary: Annotated[dict[str, SourceResult], _merge_source_results]
    new_items: list[RawTrendItem]
    enriched_items: list[EnrichedTrendItem]


def _make_collector_node(source: TrendSource, collector: Collector):
    async def node(_state: TrendGraphState) -> dict:
        try:
            items = await collector.collect()
        except Exception as exc:
            logger.exception("Collector %s failed", source.value)
            return {"raw_items": [], "run_summary": {source.value: SourceResult(source=source, error=str(exc))}}
        return {
            "raw_items": items,
            "run_summary": {source.value: SourceResult(source=source, item_count=len(items))},
        }

    return node


async def _existing_pairs(session: AsyncSession, items: list[RawTrendItem]) -> set[tuple[str, str]]:
    if not items:
        return set()
    pairs = [(item.source.value, item.url) for item in items]
    stmt = select(Trend.source, Trend.url).where(tuple_(Trend.source, Trend.url).in_(pairs))
    result = await session.execute(stmt)
    return {(row.source, row.url) for row in result}


async def _merge_and_dedupe_node(state: TrendGraphState) -> dict:
    seen: set[tuple[str, str]] = set()
    unique_items: list[RawTrendItem] = []
    for item in state["raw_items"]:
        key = (item.source.value, item.url)
        if key in seen:
            continue
        seen.add(key)
        unique_items.append(item)

    async with async_session_factory() as session:
        existing = await _existing_pairs(session, unique_items)

    new_items = [item for item in unique_items if (item.source.value, item.url) not in existing]

    new_counts_by_source: dict[str, int] = {}
    for item in new_items:
        new_counts_by_source[item.source.value] = new_counts_by_source.get(item.source.value, 0) + 1

    # Fill in new_item_count on each source's result now that dedup has run;
    # dataclasses.replace() so item_count/error set by the collector nodes
    # survive rather than being clobbered by the run_summary reducer's
    # per-key overwrite (see `_merge_source_results`).
    updated_run_summary = {
        source: dataclasses.replace(result, new_item_count=new_counts_by_source.get(source, 0))
        for source, result in state["run_summary"].items()
    }

    return {"new_items": new_items, "run_summary": updated_run_summary}


async def _enrich_with_claude_node(state: TrendGraphState) -> dict:
    enriched = await enrich_items(state["new_items"])
    return {"enriched_items": enriched}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity in [-1, 1], mapped to [0, 1] by the caller.

    Using pure Python to avoid pulling numpy into hot-path arithmetic for a
    handful of vectors — numpy is a dep, but its startup cost dominates at
    these sizes.
    """
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _score_relevance_node(state: TrendGraphState) -> dict:
    """Score each new trend against the current company's niche keywords.

    Skips scoring (leaves relevance_score=None) when no company has been
    onboarded, or when the company has no niche_keywords, or when
    embeddings fail — any of which is a legitimate operational state,
    not an error.
    """
    enriched_items = state["enriched_items"]
    if not enriched_items:
        return {}

    async with async_session_factory() as session:
        # Single-tenant assumption for MVP: use the most recently updated
        # complete company as "the" company. Multi-tenancy comes later.
        stmt = (
            select(Company)
            .where(Company.status == "complete")
            .order_by(Company.updated_at.desc())
            .limit(1)
        )
        company = (await session.execute(stmt)).scalar_one_or_none()

    if company is None or not company.niche_keywords:
        return {"enriched_items": enriched_items}

    trend_titles = [enriched.item.title for enriched in enriched_items]
    to_embed = list(company.niche_keywords) + trend_titles
    embeddings = await embed_documents(to_embed)

    keyword_count = len(company.niche_keywords)
    keyword_embeddings = embeddings[:keyword_count]
    trend_embeddings = embeddings[keyword_count:]

    valid_keyword_embeddings = [e for e in keyword_embeddings if e is not None]
    if not valid_keyword_embeddings:
        return {"enriched_items": enriched_items}

    scored: list[EnrichedTrendItem] = []
    for enriched, trend_embedding in zip(enriched_items, trend_embeddings):
        if trend_embedding is None:
            scored.append(enriched)
            continue
        # Cosine similarity is in [-1, 1]; websites usually cluster > 0, so
        # normalize to [0, 1] via (x + 1) / 2 rather than clamping — no
        # information lost and the threshold controls in the UI are natural.
        best = max(
            _cosine_similarity(trend_embedding, kw_emb) for kw_emb in valid_keyword_embeddings
        )
        scored.append(dataclasses.replace(enriched, relevance_score=(best + 1.0) / 2.0))

    return {"enriched_items": scored}


async def _upsert(session: AsyncSession, enriched_items: list[EnrichedTrendItem]) -> None:
    rows = [
        {
            "id": uuid.uuid4(),
            "source": enriched.item.source.value,
            "title": enriched.item.title,
            "description": enriched.item.description,
            "url": enriched.item.url,
            "score": enriched.item.score,
            "category": enriched.category,
            "insight": enriched.insight,
            "relevance_score": enriched.relevance_score,
            "raw_metadata": enriched.item.raw_metadata,
            "discovered_at": enriched.item.discovered_at,
        }
        for enriched in enriched_items
    ]
    dialect_name = session.bind.dialect.name if session.bind is not None else "postgresql"
    insert = postgresql.insert if dialect_name == "postgresql" else sqlite.insert
    stmt = insert(Trend).values(rows).on_conflict_do_nothing(index_elements=["source", "url"])
    await session.execute(stmt)


async def _score_relevance_per_company(session: AsyncSession, new_trend_rows: list) -> None:
    """Additive per-company relevance, computed for every `complete`
    company with niche_keywords — not just the one `_score_relevance_node`
    happened to treat as "the" company. `new_trend_rows` are freshly
    persisted `Trend` rows (already deduped upstream, so no conflict
    handling is needed — a given (company, trend) pair is scored exactly
    once, at the trend's first discovery). Degrades silently to writing no
    rows for a company when embeddings aren't configured or fail — the
    legacy `Trend.relevance_score` column already has the same limitation,
    so this isn't a new failure mode, just not (yet) fully redundant."""
    if not new_trend_rows:
        return

    companies = (
        await session.execute(select(Company).where(Company.status == "complete"))
    ).scalars().all()
    trend_titles = [row.title for row in new_trend_rows]

    for company in companies:
        if not company.niche_keywords:
            continue
        to_embed = list(company.niche_keywords) + trend_titles
        embeddings = await embed_documents(to_embed)
        keyword_count = len(company.niche_keywords)
        keyword_embeddings = [e for e in embeddings[:keyword_count] if e is not None]
        trend_embeddings = embeddings[keyword_count:]
        if not keyword_embeddings:
            continue

        rows = []
        for row, trend_embedding in zip(new_trend_rows, trend_embeddings):
            if trend_embedding is None:
                continue
            best = max(_cosine_similarity(trend_embedding, kw) for kw in keyword_embeddings)
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "company_id": company.id,
                    "trend_id": row.id,
                    "relevance_score": (best + 1.0) / 2.0,
                }
            )
        if rows:
            await session.execute(insert(CompanyTrendRelevance).values(rows))


async def _persist_node(state: TrendGraphState) -> dict:
    enriched_items = state["enriched_items"]
    if enriched_items:
        async with async_session_factory() as session:
            await _upsert(session, enriched_items)
            await session.commit()

            pairs = [(enriched.item.source.value, enriched.item.url) for enriched in enriched_items]
            new_trend_rows = (
                await session.execute(
                    select(Trend.id, Trend.title).where(tuple_(Trend.source, Trend.url).in_(pairs))
                )
            ).all()
            await _score_relevance_per_company(session, new_trend_rows)
            await session.commit()
    return {}


_DEFAULT_COLLECTORS: dict[str, tuple[TrendSource, Collector]] = {
    "collect_google_trends": (TrendSource.GOOGLE_TRENDS, GoogleTrendsCollector()),
    "collect_reddit": (TrendSource.REDDIT, RedditCollector()),
    "collect_rss": (TrendSource.RSS, RSSCollector()),
    "collect_youtube": (TrendSource.YOUTUBE, YouTubeCollector()),
    "collect_twitter": (TrendSource.TWITTER, TwitterCollector()),
    "collect_instagram": (TrendSource.INSTAGRAM, InstagramCollector()),
    "collect_tiktok": (TrendSource.TIKTOK, TikTokCollector()),
}


def _build_graph(collectors: dict[str, tuple[TrendSource, Collector]] | None = None):
    """Build the Trend Discovery graph. `collectors` defaults to the real,
    network-calling ones; tests pass stub collectors here instead of
    patching the module-level singleton, so the graph's wiring (fan-out,
    dedupe, error isolation) can be verified without touching the network or
    the Anthropic API.
    """
    graph = StateGraph(TrendGraphState)
    collectors = collectors if collectors is not None else _DEFAULT_COLLECTORS

    for node_name, (source, collector) in collectors.items():
        graph.add_node(node_name, _make_collector_node(source, collector))
    graph.add_node("merge_and_dedupe", _merge_and_dedupe_node)
    graph.add_node("enrich_with_claude", _enrich_with_claude_node)
    graph.add_node("score_relevance", _score_relevance_node)
    graph.add_node("persist", _persist_node)

    for node_name in collectors:
        graph.add_edge(START, node_name)
        graph.add_edge(node_name, "merge_and_dedupe")
    graph.add_edge("merge_and_dedupe", "enrich_with_claude")
    graph.add_edge("enrich_with_claude", "score_relevance")
    graph.add_edge("score_relevance", "persist")
    graph.add_edge("persist", END)

    return graph.compile()


_trend_graph = _build_graph()

# Last run's per-source outcome, kept in-memory for the GET /sources status
# endpoint (item counts/errors from a run aren't persisted to the DB — only
# the trends themselves are). Single-process only; fine for the APScheduler
# in-process MVP described in the build plan.
_last_run_summary: dict[str, SourceResult] = {}


def get_last_run_summary() -> dict[str, SourceResult]:
    return dict(_last_run_summary)


async def run_collection() -> RunResult:
    """Run one full Trend Discovery pass. Used by both the APScheduler job and
    the manual `POST /trend-analyzer/collect` endpoint."""
    global _last_run_summary

    initial_state: TrendGraphState = {
        "raw_items": [],
        "run_summary": {},
        "new_items": [],
        "enriched_items": [],
    }
    final_state = await _trend_graph.ainvoke(initial_state)
    _last_run_summary = dict(final_state["run_summary"])
    return RunResult(
        new_item_count=len(final_state["enriched_items"]),
        source_results=list(final_state["run_summary"].values()),
    )
