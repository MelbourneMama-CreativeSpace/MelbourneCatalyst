"""LangGraph pipeline for Strategy generation.

    START → gather_context → generate → persist → END

One-shot, synchronous — the API handler awaits `run_strategy_generation()`
directly rather than firing it via `BackgroundTasks` and polling; a single
Claude call is fast enough that a simple synchronous POST is simpler on
both ends. Same house style as `company_analyzer/graph.py`.
"""

from __future__ import annotations

import logging
import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.content_management.schemas import GeneratedStrategy
from app.agents.content_management.strategy import generate_strategy
from app.agents.trend_analyzer.relevance import ScoredTrend, fetch_scored_trends
from app.config import settings
from app.db.models import Company, Strategy
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


class StrategyGraphState(TypedDict):
    strategy_id: uuid.UUID
    company_id: uuid.UUID
    context: str
    generated: GeneratedStrategy
    status: str
    status_error: str | None


def _format_context(company: Company, trends: list[ScoredTrend]) -> str:
    lines = [
        "# Company Profile",
        f"Name: {company.name or 'Unknown'}",
        f"Industry: {company.industry or 'Unknown'}",
        f"Business model: {company.business_model or 'Unknown'}",
        f"Target audience: {company.target_audience or 'Unknown'}",
        f"Brand voice: {company.brand_voice or 'Unknown'}",
        f"Unique value proposition: {company.unique_value_prop or 'Unknown'}",
        f"Summary: {company.summary or 'Unknown'}",
    ]
    lines.append("\n# Currently Relevant Trends")
    if trends:
        lines.extend(f"- {trend.title} (relevance: {score:.2f})" for trend, score in trends)
    else:
        lines.append("None available.")
    return "\n".join(lines)


async def _gather_context_node(state: StrategyGraphState) -> dict:
    async with async_session_factory() as session:
        company = await session.get(Company, state["company_id"])
        if company is None:
            # Defensive: the API layer already 404s on an unknown company_id
            # before kicking this off — this only fires on the rare race
            # where the company is deleted mid-request.
            return {"status": "failed", "status_error": "Company not found"}

        # Ranked by this company's own relevance scores, not the legacy
        # global one — see trend_analyzer/relevance.py.
        trends = await fetch_scored_trends(
            session, state["company_id"], limit=settings.STRATEGY_MAX_TRENDS
        )

    return {"context": _format_context(company, trends)}


async def _generate_node(state: StrategyGraphState) -> dict:
    if state.get("status") == "failed":
        return {}  # gather_context already failed — nothing to generate
    generated, ok = await generate_strategy(state["context"])
    if not ok:
        return {
            "generated": generated,
            "status": "failed",
            "status_error": (
                "Strategy could not be generated (check ANTHROPIC_API_KEY / "
                "Claude API availability)."
            ),
        }
    return {"generated": generated, "status": "complete"}


async def _persist_node(state: StrategyGraphState) -> dict:
    generated = state.get("generated", GeneratedStrategy())
    final_status = state.get("status", "failed")
    status_error = state.get("status_error")

    async with async_session_factory() as session:
        strategy = await session.get(Strategy, state["strategy_id"])
        if strategy is None:
            logger.error("Strategy %s vanished mid-generation", state["strategy_id"])
            return {}

        strategy.summary = generated.summary
        strategy.marketing_strategy = generated.marketing_strategy
        strategy.campaign_direction = generated.campaign_direction
        strategy.growth_recommendations = generated.growth_recommendations
        strategy.business_suggestions = generated.business_suggestions
        strategy.status = final_status
        strategy.status_error = status_error
        await session.commit()

    return {}


def _build_graph():
    graph = StateGraph(StrategyGraphState)
    graph.add_node("gather_context", _gather_context_node)
    graph.add_node("generate", _generate_node)
    graph.add_node("persist", _persist_node)

    graph.add_edge(START, "gather_context")
    graph.add_edge("gather_context", "generate")
    graph.add_edge("generate", "persist")
    graph.add_edge("persist", END)

    return graph.compile()


_strategy_graph = _build_graph()


async def run_strategy_generation(strategy_id: uuid.UUID, company_id: uuid.UUID) -> None:
    """Run strategy generation for one Strategy row. Awaited directly by the
    API handler (not fire-and-forget). Errors are still captured onto the
    row rather than raised, so a crash mid-graph leaves a `failed` row with
    a reason instead of an orphaned `pending` one."""
    initial_state: StrategyGraphState = {
        "strategy_id": strategy_id,
        "company_id": company_id,
        "context": "",
        "generated": GeneratedStrategy(),
        "status": "pending",
        "status_error": None,
    }
    try:
        await _strategy_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("Strategy graph crashed for strategy %s", strategy_id)
        try:
            async with async_session_factory() as session:
                strategy = await session.get(Strategy, strategy_id)
                if strategy is not None:
                    strategy.status = "failed"
                    strategy.status_error = str(exc)[:512]
                    await session.commit()
        except Exception:
            logger.exception("Failed to mark strategy %s as failed", strategy_id)
