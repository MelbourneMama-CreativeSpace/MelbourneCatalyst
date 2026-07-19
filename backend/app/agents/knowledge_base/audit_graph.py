"""LangGraph pipeline for Knowledge Audit Report generation.

    START → gather_context → generate → persist → END

Same house style as `content_management/strategy_graph.py` — one-shot,
synchronous, awaited directly by the API handler.
"""

from __future__ import annotations

import logging
import uuid
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select

from app.agents.knowledge_base.audit import generate_audit
from app.agents.knowledge_base.schemas import GeneratedAudit
from app.config import settings
from app.db.models import Company, Document, KnowledgeAuditReport
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


class KnowledgeAuditGraphState(TypedDict):
    report_id: uuid.UUID
    company_id: uuid.UUID
    context: str
    document_count: int
    generated: GeneratedAudit
    status: str
    status_error: str | None


def _format_context(company: Company, documents: list[Document], document_count: int) -> str:
    lines = [
        "# Company Profile",
        f"Name: {company.name or 'Unknown'}",
        f"Industry: {company.industry or 'Unknown'}",
        f"Target audience: {company.target_audience or 'Unknown'}",
        f"Summary: {company.summary or 'Unknown'}",
    ]
    lines.append(f"\n# Knowledge Base Sample ({len(documents)} of {document_count} documents)")
    if documents:
        for doc in documents:
            lines.append(f"\n## {doc.source_type}: {doc.source_url}")
            lines.append(doc.content[:1000])
    else:
        lines.append("The knowledge base is empty — no documents have been ingested yet.")
    return "\n".join(lines)


async def _gather_context_node(state: KnowledgeAuditGraphState) -> dict:
    async with async_session_factory() as session:
        company = await session.get(Company, state["company_id"])
        if company is None:
            return {"status": "failed", "status_error": "Company not found"}

        document_count = (
            await session.execute(
                select(func.count())
                .select_from(Document)
                .where(Document.company_id == state["company_id"])
            )
        ).scalar_one()

        documents = (
            await session.execute(
                select(Document)
                .where(Document.company_id == state["company_id"])
                .order_by(Document.created_at.desc())
                .limit(settings.KNOWLEDGE_AUDIT_MAX_DOCUMENTS)
            )
        ).scalars().all()

    return {
        "context": _format_context(company, list(documents), document_count),
        "document_count": document_count,
    }


async def _generate_node(state: KnowledgeAuditGraphState) -> dict:
    if state.get("status") == "failed":
        return {}
    generated, ok = await generate_audit(state["context"])
    if not ok:
        return {
            "generated": generated,
            "status": "failed",
            "status_error": (
                "Knowledge audit could not be generated (check ANTHROPIC_API_KEY / "
                "Claude API availability)."
            ),
        }
    return {"generated": generated, "status": "complete"}


async def _persist_node(state: KnowledgeAuditGraphState) -> dict:
    generated = state.get("generated", GeneratedAudit())
    final_status = state.get("status", "failed")
    status_error = state.get("status_error")

    async with async_session_factory() as session:
        report = await session.get(KnowledgeAuditReport, state["report_id"])
        if report is None:
            logger.error("KnowledgeAuditReport %s vanished mid-generation", state["report_id"])
            return {}

        report.coverage_summary = generated.coverage_summary
        report.identified_gaps = generated.identified_gaps
        report.recommendations = generated.recommendations
        report.document_count_at_generation = state.get("document_count", 0)
        report.status = final_status
        report.status_error = status_error
        await session.commit()

    return {}


def _build_graph():
    graph = StateGraph(KnowledgeAuditGraphState)
    graph.add_node("gather_context", _gather_context_node)
    graph.add_node("generate", _generate_node)
    graph.add_node("persist", _persist_node)

    graph.add_edge(START, "gather_context")
    graph.add_edge("gather_context", "generate")
    graph.add_edge("generate", "persist")
    graph.add_edge("persist", END)

    return graph.compile()


_knowledge_audit_graph = _build_graph()


async def run_knowledge_audit_generation(report_id: uuid.UUID, company_id: uuid.UUID) -> None:
    """Run audit generation for one KnowledgeAuditReport row. Awaited
    directly by the API handler, same pattern as `run_strategy_generation`."""
    initial_state: KnowledgeAuditGraphState = {
        "report_id": report_id,
        "company_id": company_id,
        "context": "",
        "document_count": 0,
        "generated": GeneratedAudit(),
        "status": "pending",
        "status_error": None,
    }
    try:
        await _knowledge_audit_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("Knowledge audit graph crashed for report %s", report_id)
        try:
            async with async_session_factory() as session:
                report = await session.get(KnowledgeAuditReport, report_id)
                if report is not None:
                    report.status = "failed"
                    report.status_error = str(exc)[:512]
                    await session.commit()
        except Exception:
            logger.exception("Failed to mark knowledge audit report %s as failed", report_id)
