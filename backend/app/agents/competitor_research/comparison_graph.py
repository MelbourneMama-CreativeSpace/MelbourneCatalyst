"""LangGraph pipeline for Comparison generation.

    START → gather_context → generate → persist → END

Same house style as `content_management/strategy_graph.py` — one-shot,
synchronous, awaited directly by the API handler once both the Company
and the Competitor have a `status == "complete"` profile (enforced by
the endpoint, not this graph).
"""

from __future__ import annotations

import logging
import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.competitor_research.comparison import generate_comparison
from app.agents.competitor_research.schemas import GeneratedComparison
from app.db.models import Company, Competitor
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


class ComparisonGraphState(TypedDict):
    competitor_id: uuid.UUID
    company_id: uuid.UUID
    context: str
    generated: GeneratedComparison
    status: str
    status_error: str | None


def _format_profile(label: str, profile_owner: Company | Competitor) -> list[str]:
    return [
        f"# {label}: {profile_owner.name or 'Unknown'}",
        f"Industry: {profile_owner.industry or 'Unknown'}",
        f"Business model: {profile_owner.business_model or 'Unknown'}",
        f"Target audience: {profile_owner.target_audience or 'Unknown'}",
        f"Brand voice: {profile_owner.brand_voice or 'Unknown'}",
        f"Unique value proposition: {profile_owner.unique_value_prop or 'Unknown'}",
        f"Summary: {profile_owner.summary or 'Unknown'}",
    ]


def _format_context(company: Company, competitor: Competitor) -> str:
    lines = _format_profile("Company", company)
    lines.append("")
    lines.extend(_format_profile("Competitor", competitor))
    return "\n".join(lines)


async def _gather_context_node(state: ComparisonGraphState) -> dict:
    async with async_session_factory() as session:
        company = await session.get(Company, state["company_id"])
        competitor = await session.get(Competitor, state["competitor_id"])
        if company is None or competitor is None:
            return {"status": "failed", "status_error": "Company or competitor not found"}

    return {"context": _format_context(company, competitor)}


async def _generate_node(state: ComparisonGraphState) -> dict:
    if state.get("status") == "failed":
        return {}
    generated, ok = await generate_comparison(state["context"])
    if not ok:
        return {
            "generated": generated,
            "status": "failed",
            "status_error": (
                "Comparison could not be generated (check ANTHROPIC_API_KEY / "
                "Claude API availability)."
            ),
        }
    return {"generated": generated, "status": "complete"}


async def _persist_node(state: ComparisonGraphState) -> dict:
    generated = state.get("generated", GeneratedComparison())
    final_status = state.get("status", "failed")
    status_error = state.get("status_error")

    async with async_session_factory() as session:
        competitor = await session.get(Competitor, state["competitor_id"])
        if competitor is None:
            logger.error("Competitor %s vanished mid-comparison", state["competitor_id"])
            return {}

        competitor.product_pricing_comparison = generated.product_pricing_comparison
        competitor.marketing_strategy_analysis = generated.marketing_strategy_analysis
        competitor.competitive_gaps = generated.competitive_gaps
        competitor.strategic_recommendations = generated.strategic_recommendations
        competitor.comparison_status = final_status
        competitor.comparison_status_error = status_error
        await session.commit()

    return {}


def _build_graph():
    graph = StateGraph(ComparisonGraphState)
    graph.add_node("gather_context", _gather_context_node)
    graph.add_node("generate", _generate_node)
    graph.add_node("persist", _persist_node)

    graph.add_edge(START, "gather_context")
    graph.add_edge("gather_context", "generate")
    graph.add_edge("generate", "persist")
    graph.add_edge("persist", END)

    return graph.compile()


_comparison_graph = _build_graph()


async def run_comparison_generation(competitor_id: uuid.UUID, company_id: uuid.UUID) -> None:
    """Run comparison generation for one Competitor row. Awaited directly by
    the API handler (not fire-and-forget), same pattern as
    `run_strategy_generation`."""
    initial_state: ComparisonGraphState = {
        "competitor_id": competitor_id,
        "company_id": company_id,
        "context": "",
        "generated": GeneratedComparison(),
        "status": "pending",
        "status_error": None,
    }
    try:
        await _comparison_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("Comparison graph crashed for competitor %s", competitor_id)
        try:
            async with async_session_factory() as session:
                competitor = await session.get(Competitor, competitor_id)
                if competitor is not None:
                    competitor.comparison_status = "failed"
                    competitor.comparison_status_error = str(exc)[:512]
                    await session.commit()
        except Exception:
            logger.exception("Failed to mark competitor %s comparison as failed", competitor_id)
