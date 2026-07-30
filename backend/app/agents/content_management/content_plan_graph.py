"""LangGraph pipeline for Content Plan generation.

    START → gather_context → generate → persist → END

Same house style as `strategy_graph.py`. `strategy_id` is optional — a plan
can be generated straight from the company profile + trends without an
explicit prior strategy.
"""

from __future__ import annotations

import logging
import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.content_management.content_planner import (
    generate_content_plan,
    regenerate_draft_copy,
)
from app.agents.content_management.schemas import GeneratedContentPlan
from app.agents.knowledge_base.schemas import SearchHit
from app.agents.knowledge_base.search import similarity_search
from app.config import settings
from app.db.models import (
    Company,
    CompanyTrendRelevance,
    ContentItem,
    ContentItemRevision,
    ContentPlan,
    Strategy,
    Trend,
)
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


class ContentPlanGraphState(TypedDict):
    content_plan_id: uuid.UUID
    company_id: uuid.UUID
    strategy_id: uuid.UUID | None
    days: int
    context: str
    trend_ids_by_title: dict[str, uuid.UUID]
    generated: GeneratedContentPlan
    status: str
    status_error: str | None


def format_context(
    company: Company,
    strategy: Strategy | None,
    trends: list[tuple[Trend, float]],
    kb_references: list[SearchHit] | None = None,
) -> str:
    lines = [
        "# Company Profile",
        f"Name: {company.name or 'Unknown'}",
        f"Industry: {company.industry or 'Unknown'}",
        f"Target audience: {company.target_audience or 'Unknown'}",
        f"Niche keywords / audience interests: {', '.join(company.niche_keywords) if company.niche_keywords else 'Unknown'}",
        f"Brand voice: {company.brand_voice or 'Unknown'}",
        f"Summary: {company.summary or 'Unknown'}",
    ]
    if strategy is not None:
        lines.append("\n# Strategy")
        if strategy.summary:
            lines.append(strategy.summary)
        if strategy.marketing_strategy:
            lines.append(f"Marketing strategy: {strategy.marketing_strategy}")
        if strategy.campaign_direction:
            lines.append(f"Campaign direction: {strategy.campaign_direction}")

    lines.append("\n# Currently Relevant Trends")
    if trends:
        lines.extend(f"- {trend.title} (relevance: {score:.2f})" for trend, score in trends)
    else:
        lines.append("None available.")

    if kb_references:
        lines.append(
            "\n# Reference material — match this brand's real tone and style, "
            "not just its topic"
        )
        lines.extend(f"- {hit.content[:600]}" for hit in kb_references)

    return "\n".join(lines)


async def fetch_kb_references(
    session: AsyncSession, company_id: uuid.UUID, query: str, *, k: int = 3
) -> list[SearchHit]:
    """Best-effort — semantic search is Postgres-only and degrades to an
    empty list on SQLite/missing embeddings (see `similarity_search`'s own
    docstring), so generation still works without reference material
    rather than failing the whole plan over it."""
    return await similarity_search(session, query, company_id=company_id, k=k)


async def _gather_context_node(state: ContentPlanGraphState) -> dict:
    async with async_session_factory() as session:
        company = await session.get(Company, state["company_id"])
        if company is None:
            # Defensive: the API layer already 404s before kicking this off.
            return {"status": "failed", "status_error": "Company not found"}

        strategy = None
        if state["strategy_id"] is not None:
            strategy = await session.get(Strategy, state["strategy_id"])

        # Prefer this company's own relevance scores (CompanyTrendRelevance)
        # — falls back to the legacy global Trend.relevance_score when this
        # company has no scored trends yet (e.g. onboarded after the last
        # collection run, or embeddings were never configured). See
        # CompanyTrendRelevance's docstring in db/models.py: a single global
        # score per trend stopped being reliable once more than one company
        # is onboarded, which is exactly the case this falls back for.
        per_company_rows = (
            await session.execute(
                select(Trend, CompanyTrendRelevance.relevance_score)
                .join(CompanyTrendRelevance, CompanyTrendRelevance.trend_id == Trend.id)
                .where(CompanyTrendRelevance.company_id == state["company_id"])
                .order_by(CompanyTrendRelevance.relevance_score.desc())
                .limit(settings.CONTENT_PLAN_MAX_TRENDS)
            )
        ).all()

        if per_company_rows:
            trends_with_scores: list[tuple[Trend, float]] = [(row[0], row[1]) for row in per_company_rows]
        else:
            legacy_trends = (
                await session.execute(
                    select(Trend)
                    .where(Trend.relevance_score.is_not(None))
                    .order_by(Trend.relevance_score.desc())
                    .limit(settings.CONTENT_PLAN_MAX_TRENDS)
                )
            ).scalars().all()
            trends_with_scores = [(trend, trend.relevance_score) for trend in legacy_trends]

        # General style-reference query (not topic-specific, since a whole
        # plan spans many themes) — company summary/industry is a reasonable
        # proxy for "what does this brand's own real content sound like."
        reference_query = " ".join(
            filter(None, [company.summary, company.industry, company.name])
        ) or (company.name or "")
        kb_references = (
            await fetch_kb_references(session, state["company_id"], reference_query)
            if reference_query
            else []
        )

    return {
        "context": format_context(company, strategy, trends_with_scores, kb_references),
        "trend_ids_by_title": {trend.title: trend.id for trend, _ in trends_with_scores},
    }


async def _generate_node(state: ContentPlanGraphState) -> dict:
    if state.get("status") == "failed":
        return {}
    generated, ok = await generate_content_plan(state["context"], days=state["days"])
    if not ok:
        return {
            "generated": generated,
            "status": "failed",
            "status_error": (
                "Content plan could not be generated (check ANTHROPIC_API_KEY / "
                "Claude API availability)."
            ),
        }
    return {"generated": generated, "status": "complete"}


async def _persist_node(state: ContentPlanGraphState) -> dict:
    generated = state.get("generated", GeneratedContentPlan())
    final_status = state.get("status", "failed")
    status_error = state.get("status_error")
    trend_ids_by_title = state.get("trend_ids_by_title", {})

    async with async_session_factory() as session:
        content_plan = await session.get(ContentPlan, state["content_plan_id"])
        if content_plan is None:
            logger.error("ContentPlan %s vanished mid-generation", state["content_plan_id"])
            return {}

        content_plan.status = final_status
        content_plan.status_error = status_error

        session.add_all(
            [
                ContentItem(
                    id=uuid.uuid4(),
                    content_plan_id=content_plan.id,
                    title=item.title,
                    description=item.description,
                    content_type=item.content_type,
                    platform=item.platform,
                    theme=item.theme,
                    suggested_date=item.suggested_date,
                    source_trend_id=(
                        trend_ids_by_title.get(item.related_trend_title)
                        if item.related_trend_title
                        else None
                    ),
                    audience_interest=item.audience_interest,
                    seasonal_event=item.seasonal_event,
                    draft_copy=item.draft_copy,
                    hashtags=item.hashtags,
                    approval_status="pending",
                )
                for item in generated.items
            ]
        )

        await session.commit()

    return {}


def _build_graph():
    graph = StateGraph(ContentPlanGraphState)
    graph.add_node("gather_context", _gather_context_node)
    graph.add_node("generate", _generate_node)
    graph.add_node("persist", _persist_node)

    graph.add_edge(START, "gather_context")
    graph.add_edge("gather_context", "generate")
    graph.add_edge("generate", "persist")
    graph.add_edge("persist", END)

    return graph.compile()


_content_plan_graph = _build_graph()


async def run_content_plan_generation(
    content_plan_id: uuid.UUID,
    company_id: uuid.UUID,
    strategy_id: uuid.UUID | None,
    days: int | None = None,
) -> None:
    """Run content plan generation for one ContentPlan row. Awaited directly
    by the API handler, same pattern as `run_strategy_generation`. `days`
    overrides the default window (e.g. 7 for a weekly plan, 30 for a
    monthly one) — falls back to `settings.CONTENT_PLAN_DAYS` when omitted."""
    initial_state: ContentPlanGraphState = {
        "content_plan_id": content_plan_id,
        "company_id": company_id,
        "strategy_id": strategy_id,
        "days": days if days is not None else settings.CONTENT_PLAN_DAYS,
        "context": "",
        "trend_ids_by_title": {},
        "generated": GeneratedContentPlan(),
        "status": "pending",
        "status_error": None,
    }
    try:
        await _content_plan_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("Content plan graph crashed for plan %s", content_plan_id)
        try:
            async with async_session_factory() as session:
                content_plan = await session.get(ContentPlan, content_plan_id)
                if content_plan is not None:
                    content_plan.status = "failed"
                    content_plan.status_error = str(exc)[:512]
                    await session.commit()
        except Exception:
            logger.exception("Failed to mark content plan %s as failed", content_plan_id)


async def regenerate_item_draft_copy(item_id: uuid.UUID) -> tuple[ContentItem | None, bool]:
    """Rewrite one existing ContentItem's `draft_copy` in place — the UI's
    "regenerate" action. Not a graph (no multi-step state to track for a
    single Claude call over an existing row) — a plain async function is
    simpler and matches the size of the job. Returns `(item, True)` on
    success, `(item, False)` if generation failed (item is left
    unchanged), or `(None, False)` if the item doesn't exist."""
    async with async_session_factory() as session:
        item = await session.get(ContentItem, item_id)
        if item is None:
            return None, False

        content_plan = await session.get(ContentPlan, item.content_plan_id)
        company = await session.get(Company, content_plan.company_id) if content_plan else None
        strategy = (
            await session.get(Strategy, content_plan.strategy_id)
            if content_plan and content_plan.strategy_id
            else None
        )
        if company is None:
            logger.error("Company for content item %s vanished", item_id)
            return item, False

        context = format_context(company, strategy, [])
        draft_copy, ok = await regenerate_draft_copy(
            context, item.title, item.description, item.content_type, item.platform
        )
        if not ok:
            return item, False

        # Snapshot the pre-regeneration draft, same as a manual edit does —
        # a Claude regeneration shouldn't be able to lose a draft any more
        # silently than a hand-edit can.
        if item.draft_copy is not None:
            session.add(
                ContentItemRevision(
                    id=uuid.uuid4(),
                    content_item_id=item.id,
                    draft_copy=item.draft_copy,
                    edited_by="AI regeneration",
                )
            )
        item.draft_copy = draft_copy
        await session.commit()
        await session.refresh(item)
        return item, True
