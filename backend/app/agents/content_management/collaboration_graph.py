"""LangGraph pipeline for Collaboration generation.

    START → gather_context → generate → persist → END

Same house style as `content_plan_graph.py`. `strategy_id` is optional — a
collaboration plan can be generated straight from the company profile +
trends without an explicit prior strategy.
"""

from __future__ import annotations

import logging
import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.agents.content_management.collaboration import generate_collaboration
from app.agents.content_management.schemas import GeneratedCollaboration
from app.agents.trend_analyzer.relevance import ScoredTrend, fetch_scored_trends
from app.config import settings
from app.db.models import Collaboration, CollaborationIdea, Company, Strategy
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


class CollaborationGraphState(TypedDict):
    collaboration_id: uuid.UUID
    company_id: uuid.UUID
    strategy_id: uuid.UUID | None
    context: str
    generated: GeneratedCollaboration
    status: str
    status_error: str | None


def _format_context(company: Company, strategy: Strategy | None, trends: list[ScoredTrend]) -> str:
    lines = [
        "# Company Profile",
        f"Name: {company.name or 'Unknown'}",
        f"Industry: {company.industry or 'Unknown'}",
        f"Target audience: {company.target_audience or 'Unknown'}",
        f"Brand voice: {company.brand_voice or 'Unknown'}",
        f"Summary: {company.summary or 'Unknown'}",
    ]
    if strategy is not None:
        lines.append("\n# Strategy")
        if strategy.summary:
            lines.append(strategy.summary)
        if strategy.marketing_strategy:
            lines.append(f"Marketing strategy: {strategy.marketing_strategy}")

    lines.append("\n# Currently Relevant Trends")
    if trends:
        lines.extend(f"- {trend.title} (relevance: {score:.2f})" for trend, score in trends)
    else:
        lines.append("None available.")
    return "\n".join(lines)


async def _gather_context_node(state: CollaborationGraphState) -> dict:
    async with async_session_factory() as session:
        company = await session.get(Company, state["company_id"])
        if company is None:
            return {"status": "failed", "status_error": "Company not found"}

        strategy = None
        if state["strategy_id"] is not None:
            strategy = await session.get(Strategy, state["strategy_id"])

        # Ranked by this company's own relevance scores, not the legacy
        # global one — see trend_analyzer/relevance.py.
        trends = await fetch_scored_trends(
            session, state["company_id"], limit=settings.STRATEGY_MAX_TRENDS
        )

    return {"context": _format_context(company, strategy, trends)}


async def _generate_node(state: CollaborationGraphState) -> dict:
    if state.get("status") == "failed":
        return {}
    generated, ok = await generate_collaboration(state["context"])
    if not ok:
        return {
            "generated": generated,
            "status": "failed",
            "status_error": (
                "Collaboration ideas could not be generated (check ANTHROPIC_API_KEY / "
                "Claude API availability)."
            ),
        }
    return {"generated": generated, "status": "complete"}


async def _persist_node(state: CollaborationGraphState) -> dict:
    generated = state.get("generated", GeneratedCollaboration())
    final_status = state.get("status", "failed")
    status_error = state.get("status_error")

    async with async_session_factory() as session:
        collaboration = await session.get(Collaboration, state["collaboration_id"])
        if collaboration is None:
            logger.error("Collaboration %s vanished mid-generation", state["collaboration_id"])
            return {}

        collaboration.status = final_status
        collaboration.status_error = status_error

        session.add_all(
            [
                CollaborationIdea(
                    id=uuid.uuid4(),
                    collaboration_id=collaboration.id,
                    collaborator_archetype=idea.collaborator_archetype,
                    partnership_angle=idea.partnership_angle,
                    outreach_template=idea.outreach_template,
                    priority=idea.priority,
                    rationale=idea.rationale,
                )
                for idea in generated.ideas
            ]
        )

        await session.commit()

    return {}


def _build_graph():
    graph = StateGraph(CollaborationGraphState)
    graph.add_node("gather_context", _gather_context_node)
    graph.add_node("generate", _generate_node)
    graph.add_node("persist", _persist_node)

    graph.add_edge(START, "gather_context")
    graph.add_edge("gather_context", "generate")
    graph.add_edge("generate", "persist")
    graph.add_edge("persist", END)

    return graph.compile()


_collaboration_graph = _build_graph()


async def run_collaboration_generation(
    collaboration_id: uuid.UUID, company_id: uuid.UUID, strategy_id: uuid.UUID | None
) -> None:
    """Run collaboration generation for one Collaboration row. Awaited
    directly by the API handler, same pattern as `run_content_plan_generation`."""
    initial_state: CollaborationGraphState = {
        "collaboration_id": collaboration_id,
        "company_id": company_id,
        "strategy_id": strategy_id,
        "context": "",
        "generated": GeneratedCollaboration(),
        "status": "pending",
        "status_error": None,
    }
    try:
        await _collaboration_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("Collaboration graph crashed for collaboration %s", collaboration_id)
        try:
            async with async_session_factory() as session:
                collaboration = await session.get(Collaboration, collaboration_id)
                if collaboration is not None:
                    collaboration.status = "failed"
                    collaboration.status_error = str(exc)[:512]
                    await session.commit()
        except Exception:
            logger.exception("Failed to mark collaboration %s as failed", collaboration_id)
