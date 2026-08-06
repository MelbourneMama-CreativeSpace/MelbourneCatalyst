"""LangGraph pipeline for Campaign generation.

    START → gather_context → generate → persist → END

Same house style as `strategy_graph.py`/`content_plan_graph.py` — one-shot,
synchronous, awaited directly by the API handler. `content_plan_id` and
`strategy_id` are both optional; when a content plan is given, its items'
date range seeds the suggested campaign timeline in the context so Claude
has a concrete anchor instead of guessing dates from nothing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agents.content_management.campaign import generate_campaign
from app.agents.content_management.schemas import GeneratedCampaign
from app.agents.trend_analyzer.relevance import ScoredTrend, fetch_scored_trends
from app.config import settings
from app.db.models import Campaign, Company, ContentPlan, Strategy
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


class CampaignGraphState(TypedDict):
    campaign_id: uuid.UUID
    company_id: uuid.UUID
    content_plan_id: uuid.UUID | None
    strategy_id: uuid.UUID | None
    context: str
    generated: GeneratedCampaign
    status: str
    status_error: str | None


def _format_context(
    company: Company,
    strategy: Strategy | None,
    content_plan: ContentPlan | None,
    trends: list[ScoredTrend],
) -> str:
    lines = [
        f"Today's date, for reference: {date.today().isoformat()}",
        "\n# Company Profile",
        f"Name: {company.name or 'Unknown'}",
        f"Industry: {company.industry or 'Unknown'}",
        f"Target audience: {company.target_audience or 'Unknown'}",
        f"Summary: {company.summary or 'Unknown'}",
    ]
    if strategy is not None:
        lines.append("\n# Strategy")
        if strategy.summary:
            lines.append(strategy.summary)
        if strategy.marketing_strategy:
            lines.append(f"Marketing strategy: {strategy.marketing_strategy}")

    if content_plan is not None and content_plan.items:
        dates = [item.suggested_date for item in content_plan.items]
        lines.append("\n# Content Calendar")
        lines.append(f"Date range: {min(dates).isoformat()} to {max(dates).isoformat()}")
        lines.append(f"{len(content_plan.items)} planned content items across this range.")

    lines.append("\n# Currently Relevant Trends")
    if trends:
        lines.extend(f"- {trend.title} (relevance: {score:.2f})" for trend, score in trends)
    else:
        lines.append("None available.")
    return "\n".join(lines)


async def _gather_context_node(state: CampaignGraphState) -> dict:
    async with async_session_factory() as session:
        company = await session.get(Company, state["company_id"])
        if company is None:
            return {"status": "failed", "status_error": "Company not found"}

        strategy = None
        if state["strategy_id"] is not None:
            strategy = await session.get(Strategy, state["strategy_id"])

        content_plan = None
        if state["content_plan_id"] is not None:
            content_plan = (
                await session.execute(
                    select(ContentPlan)
                    .options(selectinload(ContentPlan.items))
                    .where(ContentPlan.id == state["content_plan_id"])
                )
            ).scalar_one_or_none()

        # Ranked by this company's own relevance scores, not the legacy
        # global one — see trend_analyzer/relevance.py.
        trends = await fetch_scored_trends(
            session, state["company_id"], limit=settings.STRATEGY_MAX_TRENDS
        )

    return {"context": _format_context(company, strategy, content_plan, trends)}


async def _generate_node(state: CampaignGraphState) -> dict:
    if state.get("status") == "failed":
        return {}
    generated, ok = await generate_campaign(state["context"])
    if not ok:
        return {
            "generated": generated,
            "status": "failed",
            "status_error": (
                "Campaign could not be generated (check ANTHROPIC_API_KEY / "
                "Claude API availability)."
            ),
        }
    return {"generated": generated, "status": "complete"}


async def _persist_node(state: CampaignGraphState) -> dict:
    generated = state.get("generated", GeneratedCampaign())
    final_status = state.get("status", "failed")
    status_error = state.get("status_error")

    async with async_session_factory() as session:
        campaign = await session.get(Campaign, state["campaign_id"])
        if campaign is None:
            logger.error("Campaign %s vanished mid-generation", state["campaign_id"])
            return {}

        campaign.name = generated.name
        campaign.objective = generated.objective
        campaign.budget_allocation = generated.budget_allocation
        campaign.success_metrics = generated.success_metrics
        campaign.start_date = generated.start_date
        campaign.end_date = generated.end_date
        campaign.status = final_status
        campaign.status_error = status_error
        await session.commit()

    return {}


def _build_graph():
    graph = StateGraph(CampaignGraphState)
    graph.add_node("gather_context", _gather_context_node)
    graph.add_node("generate", _generate_node)
    graph.add_node("persist", _persist_node)

    graph.add_edge(START, "gather_context")
    graph.add_edge("gather_context", "generate")
    graph.add_edge("generate", "persist")
    graph.add_edge("persist", END)

    return graph.compile()


_campaign_graph = _build_graph()


async def run_campaign_generation(
    campaign_id: uuid.UUID,
    company_id: uuid.UUID,
    content_plan_id: uuid.UUID | None,
    strategy_id: uuid.UUID | None,
) -> None:
    """Run campaign generation for one Campaign row. Awaited directly by the
    API handler, same pattern as `run_strategy_generation`."""
    initial_state: CampaignGraphState = {
        "campaign_id": campaign_id,
        "company_id": company_id,
        "content_plan_id": content_plan_id,
        "strategy_id": strategy_id,
        "context": "",
        "generated": GeneratedCampaign(),
        "status": "pending",
        "status_error": None,
    }
    try:
        await _campaign_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("Campaign graph crashed for campaign %s", campaign_id)
        try:
            async with async_session_factory() as session:
                campaign = await session.get(Campaign, campaign_id)
                if campaign is not None:
                    campaign.status = "failed"
                    campaign.status_error = str(exc)[:512]
                    await session.commit()
        except Exception:
            logger.exception("Failed to mark campaign %s as failed", campaign_id)
