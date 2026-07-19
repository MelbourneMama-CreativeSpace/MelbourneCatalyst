"""LangGraph pipeline for Trend Report generation.

    START → gather_context → generate → persist → END

Same house style as `content_management/strategy_graph.py` — one-shot,
synchronous, awaited directly by the API handler.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.agents.trend_analyzer.report import generate_trend_report
from app.agents.trend_analyzer.schemas import GeneratedTrendReport
from app.config import settings
from app.db.models import Company, Trend, TrendReport
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


class TrendReportGraphState(TypedDict):
    report_id: uuid.UUID
    company_id: uuid.UUID
    period_days: int
    context: str
    generated: GeneratedTrendReport
    status: str
    status_error: str | None


def _format_context(company: Company, trends: list[Trend], period_days: int) -> str:
    lines = [
        f"# Company Profile (report covers the last {period_days} days)",
        f"Name: {company.name or 'Unknown'}",
        f"Industry: {company.industry or 'Unknown'}",
        f"Target audience: {company.target_audience or 'Unknown'}",
        f"Summary: {company.summary or 'Unknown'}",
    ]
    lines.append("\n# Relevant Trends From This Period")
    if trends:
        lines.extend(
            f"- {trend.title} (relevance: {trend.relevance_score:.2f}, "
            f"discovered: {trend.discovered_at.date().isoformat()})"
            for trend in trends
        )
    else:
        lines.append("None available — no relevance-scored trends were discovered in this period.")
    return "\n".join(lines)


async def _gather_context_node(state: TrendReportGraphState) -> dict:
    async with async_session_factory() as session:
        company = await session.get(Company, state["company_id"])
        if company is None:
            return {"status": "failed", "status_error": "Company not found"}

        cutoff = datetime.now(timezone.utc) - timedelta(days=state["period_days"])
        trends = (
            await session.execute(
                select(Trend)
                .where(Trend.relevance_score.is_not(None), Trend.discovered_at >= cutoff)
                .order_by(Trend.relevance_score.desc())
                .limit(settings.TREND_REPORT_MAX_TRENDS)
            )
        ).scalars().all()

    return {"context": _format_context(company, list(trends), state["period_days"])}


async def _generate_node(state: TrendReportGraphState) -> dict:
    if state.get("status") == "failed":
        return {}
    generated, ok = await generate_trend_report(state["context"])
    if not ok:
        return {
            "generated": generated,
            "status": "failed",
            "status_error": (
                "Trend report could not be generated (check ANTHROPIC_API_KEY / "
                "Claude API availability)."
            ),
        }
    return {"generated": generated, "status": "complete"}


async def _persist_node(state: TrendReportGraphState) -> dict:
    generated = state.get("generated", GeneratedTrendReport())
    final_status = state.get("status", "failed")
    status_error = state.get("status_error")

    async with async_session_factory() as session:
        report = await session.get(TrendReport, state["report_id"])
        if report is None:
            logger.error("TrendReport %s vanished mid-generation", state["report_id"])
            return {}

        report.summary = generated.summary
        report.key_themes = generated.key_themes or None
        report.notable_trends_summary = generated.notable_trends_summary
        report.content_opportunities = generated.content_opportunities
        report.status = final_status
        report.status_error = status_error
        await session.commit()

    return {}


def _build_graph():
    graph = StateGraph(TrendReportGraphState)
    graph.add_node("gather_context", _gather_context_node)
    graph.add_node("generate", _generate_node)
    graph.add_node("persist", _persist_node)

    graph.add_edge(START, "gather_context")
    graph.add_edge("gather_context", "generate")
    graph.add_edge("generate", "persist")
    graph.add_edge("persist", END)

    return graph.compile()


_trend_report_graph = _build_graph()


async def run_trend_report_generation(
    report_id: uuid.UUID, company_id: uuid.UUID, period_days: int
) -> None:
    """Run trend report generation for one TrendReport row. Awaited
    directly by the API handler, same pattern as `run_strategy_generation`."""
    initial_state: TrendReportGraphState = {
        "report_id": report_id,
        "company_id": company_id,
        "period_days": period_days,
        "context": "",
        "generated": GeneratedTrendReport(),
        "status": "pending",
        "status_error": None,
    }
    try:
        await _trend_report_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("Trend report graph crashed for report %s", report_id)
        try:
            async with async_session_factory() as session:
                report = await session.get(TrendReport, report_id)
                if report is not None:
                    report.status = "failed"
                    report.status_error = str(exc)[:512]
                    await session.commit()
        except Exception:
            logger.exception("Failed to mark trend report %s as failed", report_id)
