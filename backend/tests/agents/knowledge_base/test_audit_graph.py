"""Tests for the Knowledge Audit LangGraph pipeline."""

from __future__ import annotations

import uuid

from app.agents.knowledge_base import audit_graph as graph_module
from app.agents.knowledge_base.schemas import GeneratedAudit
from app.db.models import Company, Document, KnowledgeAuditReport


async def _stub_generate_audit(context: str):
    return (
        GeneratedAudit(
            coverage_summary="Covers the homepage.",
            identified_gaps="Missing pricing content.",
            recommendations="Ingest the pricing page.",
        ),
        True,
    )


async def _stub_generate_audit_failed(context: str):
    return GeneratedAudit(), False


async def test_run_knowledge_audit_generation_persists_a_complete_report(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_audit", _stub_generate_audit)

    company_id = uuid.uuid4()
    report_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(
            Document(
                id=uuid.uuid4(),
                company_id=company_id,
                source_type="website",
                source_url="https://example.com/",
                chunk_index=0,
                content="Acme sells widgets to marketers.",
                raw_metadata={},
            )
        )
        session.add(KnowledgeAuditReport(id=report_id, company_id=company_id, status="pending"))
        await session.commit()

    await graph_module.run_knowledge_audit_generation(report_id, company_id)

    async with test_session_factory() as session:
        report = await session.get(KnowledgeAuditReport, report_id)

    assert report.status == "complete"
    assert report.coverage_summary == "Covers the homepage."
    assert report.document_count_at_generation == 1


async def test_run_knowledge_audit_generation_handles_an_empty_kb(monkeypatch, test_session_factory):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    captured_context = {}

    async def _capturing_generate(context: str):
        captured_context["value"] = context
        return GeneratedAudit(), True

    monkeypatch.setattr(graph_module, "generate_audit", _capturing_generate)

    company_id = uuid.uuid4()
    report_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(KnowledgeAuditReport(id=report_id, company_id=company_id, status="pending"))
        await session.commit()

    await graph_module.run_knowledge_audit_generation(report_id, company_id)

    assert "empty" in captured_context["value"].lower()

    async with test_session_factory() as session:
        report = await session.get(KnowledgeAuditReport, report_id)
    assert report.document_count_at_generation == 0


async def test_run_knowledge_audit_generation_marks_failed_on_generation_failure(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_audit", _stub_generate_audit_failed)

    company_id = uuid.uuid4()
    report_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        session.add(KnowledgeAuditReport(id=report_id, company_id=company_id, status="pending"))
        await session.commit()

    await graph_module.run_knowledge_audit_generation(report_id, company_id)

    async with test_session_factory() as session:
        report = await session.get(KnowledgeAuditReport, report_id)

    assert report.status == "failed"
    assert report.status_error is not None


async def test_run_knowledge_audit_generation_marks_failed_when_company_missing(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_audit", _stub_generate_audit)

    report_id = uuid.uuid4()
    missing_company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(KnowledgeAuditReport(id=report_id, company_id=missing_company_id, status="pending"))
        await session.commit()

    await graph_module.run_knowledge_audit_generation(report_id, missing_company_id)

    async with test_session_factory() as session:
        report = await session.get(KnowledgeAuditReport, report_id)

    assert report.status == "failed"
    assert report.status_error == "Company not found"
