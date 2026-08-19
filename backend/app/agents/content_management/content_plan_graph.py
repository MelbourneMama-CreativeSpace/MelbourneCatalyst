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
    generate_content_item_from_input,
    generate_content_plan,
    regenerate_draft_copy,
)
from app.agents.content_management.schemas import GeneratedContentPlan
from app.agents.knowledge_base.schemas import SearchHit
from app.agents.knowledge_base.search import similarity_search
from app.agents.trend_analyzer.relevance import ScoredTrend, fetch_scored_trends
from app.config import settings
from app.db.models import (
    Company,
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
    trends: list[ScoredTrend],
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
        # `insight` (why this trend matters, not just its title) is the
        # actual substance worth writing content around — dropped
        # entirely before, even though it's exactly what a caller asking
        # for content "about this trend" needs to work from.
        for trend, score in trends:
            line = f"- {trend.title} (relevance: {score:.2f})"
            if trend.insight:
                line += f" — {trend.insight}"
            lines.append(line)
    else:
        lines.append("None available.")

    if kb_references:
        lines.append(
            "\n# Reference material — match this brand's real tone and style, "
            "not just its topic"
        )
        lines.extend(f"- {hit.content[:600]}" for hit in kb_references)

    return "\n".join(lines)


def format_reference_context(inspired_by_handle: str, trends: list[ScoredTrend]) -> str:
    """Context for content inspired by / about an *external* account
    (`inspired_by_handle`) rather than this company's own organic content
    — deliberately does NOT include format_context's company profile,
    brand voice, or KB references at all. Real bug this fixes: content
    generated for "give me a reel idea for @other_handle" used to get
    this company's own industry/brand-voice/summary and a semantic
    search over this company's own knowledge base injected as generation
    context — irrelevant at best (a different account's content has
    nothing to do with this company's brand voice) and actively
    misleading at worst (this company's real private KB content bleeding
    into a draft about someone else's account). The model already has
    the account's own bio/recent-posts/niche from analyze_social_profile
    earlier in the conversation — that's the only "profile" this prompt
    needs, and it's already in the conversation, not repeated here.
    """
    lines = [
        f"# Reference account: {inspired_by_handle}",
        "This content is inspired by / about the external account above, NOT this "
        "company's own brand — do not use this company's industry, brand voice, or "
        "knowledge base (none is included here on purpose). Write in a way consistent "
        "with what's already been established about this account earlier in the "
        "conversation (its bio, recent posts, niche, presentation style, tone).",
    ]
    lines.append("\n# Currently Relevant Trends")
    if trends:
        for trend, score in trends:
            line = f"- {trend.title} (relevance: {score:.2f})"
            if trend.insight:
                line += f" — {trend.insight}"
            lines.append(line)
    else:
        lines.append("None available.")
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

        # This prefer-per-company-then-fall-back-to-global read used to
        # live here and only here; it now lives in
        # trend_analyzer/relevance.py, shared with the five other callers
        # that were still reading the legacy global score.
        trends_with_scores = await fetch_scored_trends(
            session, state["company_id"], limit=settings.CONTENT_PLAN_MAX_TRENDS
        )

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


async def create_manual_item(
    company_id: uuid.UUID,
    topic: str,
    platform: str,
    content_type: str,
    media_url: str | None = None,
    trend_id: uuid.UUID | None = None,
    inspired_by_handle: str | None = None,
) -> tuple[ContentItem | None, bool]:
    """Generate one ad-hoc ContentItem from a free-text brief and persist it
    into the company's manual plan — the single-post counterpart to
    `run_content_plan_generation`'s whole-calendar generation. Shared by the
    manual-item HTTP endpoint and the chat agent's `create_content_item`
    write tool, so "describe a post in chat" and "fill in the manual-item
    form" produce identical results through one code path. Manages its own
    session, same pattern as `regenerate_item_draft_copy` — callers that
    already hold a session (e.g. an endpoint doing its own ownership check
    first) are expected to, this never touches theirs. `media_url` carries
    an image already attached elsewhere (e.g. a chat attachment) straight
    onto the new item — the caller resolves it, this just persists it.

    The company's own top-relevant current trends are always included as
    ambient context now — this used to be hardcoded to an empty list, so
    a manual/chat-written post had *zero* trend awareness even though the
    exact same relevance-scored data already existed and was already used
    for the bulk content-plan generator. `trend_id` goes further: it
    explicitly centers generation on one specific trend (e.g. the user
    picked one off `list_trending_topics`), guaranteed to be represented
    in context regardless of whether it'd make the ambient top-N cut on
    relevance alone, and the resulting item's `source_trend_id` is set to
    it — the same linkage `run_content_plan_generation` already gives its
    own trend-inspired items. An unknown/invalid `trend_id` degrades to
    the ambient-only behavior rather than failing the whole generation.

    `inspired_by_handle` marks this item as inspired by / about an
    *external* account (set whenever the chat agent is drafting
    something based on an analyze_social_profile lookup, not this
    company's own organic content) — when set, this company's own
    profile/brand-voice/KB context is deliberately NOT included (see
    `format_reference_context`; real bug this fixes: that context used
    to always get injected regardless, and the resulting item was
    otherwise indistinguishable from this company's own genuine content
    once persisted, publishable through this company's own connected
    accounts as if it were their own) and the ambient company-relevance
    trend scoring is skipped too (irrelevant to a different account's
    niche) — an explicit `trend_id` still applies, since that's a
    specific choice, not company-scoped ambient context.

    Returns `(None, False)` if the company doesn't exist, isn't ready, or
    generation itself fails."""
    async with async_session_factory() as session:
        company = await session.get(Company, company_id)
        if company is None or company.status != "complete":
            return None, False

        # Same "one reusable plan per company for everything not part of a
        # real generated calendar" shape as the manual-item endpoint's own
        # `_get_or_create_manual_plan` — duplicated rather than imported
        # across the endpoint/agent boundary, since it's a few lines and
        # this module already owns every other piece of manual-item
        # generation.
        manual_plan = (
            await session.execute(
                select(ContentPlan).where(
                    ContentPlan.company_id == company_id, ContentPlan.is_manual.is_(True)
                )
            )
        ).scalar_one_or_none()
        if manual_plan is None:
            manual_plan = ContentPlan(
                id=uuid.uuid4(), company_id=company_id, status="complete", is_manual=True
            )
            session.add(manual_plan)
            await session.flush()

        # Ambient company-relevance trend scoring only applies to this
        # company's own content — a different account's niche isn't
        # scored against this company's niche_keywords, so it's not
        # meaningful context for inspired_by_handle content. An explicit
        # trend_id below still applies either way; that's a specific
        # choice being made, not ambient company-scoped context.
        trends_with_scores = (
            []
            if inspired_by_handle is not None
            else await fetch_scored_trends(session, company_id, limit=settings.MANUAL_ITEM_MAX_TRENDS)
        )

        source_trend: Trend | None = None
        if trend_id is not None:
            source_trend = await session.get(Trend, trend_id)
            if source_trend is not None and source_trend.id not in {
                t.id for t, _ in trends_with_scores
            }:
                trends_with_scores = [
                    (source_trend, source_trend.relevance_score or 0.0)
                ] + trends_with_scores

        if inspired_by_handle is not None:
            # Deliberately no fetch_kb_references call here — this
            # company's own knowledge base has nothing to do with a
            # different account's content, and searching it anyway is
            # exactly the bug this whole parameter exists to fix.
            context = format_reference_context(inspired_by_handle, trends_with_scores)
        else:
            kb_references = await fetch_kb_references(session, company_id, topic)
            context = format_context(company, None, trends_with_scores, kb_references)

        effective_topic = topic
        if source_trend is not None:
            steer = f'Write this specifically inspired by the trend "{source_trend.title}"'
            if source_trend.insight:
                steer += f" — {source_trend.insight}"
            effective_topic = f"{steer}.\n\n{topic}"

        generated, ok = await generate_content_item_from_input(
            context, effective_topic, platform, content_type
        )
        if not ok or generated is None:
            return None, False

        item = ContentItem(
            id=uuid.uuid4(),
            content_plan_id=manual_plan.id,
            title=generated.title,
            description=generated.description,
            content_type=generated.content_type,
            platform=generated.platform,
            theme=generated.theme,
            suggested_date=generated.suggested_date,
            draft_copy=generated.draft_copy,
            hashtags=generated.hashtags,
            media_url=media_url,
            source_trend_id=source_trend.id if source_trend is not None else None,
            inspired_by_handle=inspired_by_handle,
            approval_status="pending",
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item, True
