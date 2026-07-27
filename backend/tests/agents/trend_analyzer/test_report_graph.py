"""Tests for the Trend Report LangGraph pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.agents.trend_analyzer import report_graph as graph_module
from app.agents.trend_analyzer.schemas import GeneratedTrendReport
from app.db.models import Campaign, Company, Competitor, Trend, TrendReport


async def _stub_generate_trend_report(context: str):
    return (
        GeneratedTrendReport(
            summary="Strong week for AI marketing tools.",
            key_themes=["AI automation", "video content"],
            notable_trends_summary="AI copywriting tools trending.",
            content_opportunities="Post an AI workflow demo.",
            campaign_alignment_notes="Builds on your Spring Launch campaign.",
            competitor_relevance_notes="No competitor has covered this yet.",
        ),
        True,
    )


async def _stub_generate_trend_report_failed(context: str):
    return GeneratedTrendReport(), False


async def test_run_trend_report_generation_persists_a_complete_report(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_trend_report", _stub_generate_trend_report)

    company_id = uuid.uuid4()
    report_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(TrendReport(id=report_id, company_id=company_id, status="pending", period_days=7))
        await session.commit()

    await graph_module.run_trend_report_generation(report_id, company_id, 7)

    async with test_session_factory() as session:
        report = await session.get(TrendReport, report_id)

    assert report.status == "complete"
    assert report.summary == "Strong week for AI marketing tools."
    assert report.key_themes == ["AI automation", "video content"]
    assert report.campaign_alignment_notes == "Builds on your Spring Launch campaign."
    assert report.competitor_relevance_notes == "No competitor has covered this yet."


async def test_gather_context_includes_recent_campaigns_and_competitors(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(
            Campaign(
                id=uuid.uuid4(),
                company_id=company_id,
                status="complete",
                name="Spring Launch",
                objective="Drive signups for the new product line.",
            )
        )
        session.add(
            Competitor(
                id=uuid.uuid4(),
                company_id=company_id,
                url="https://rival.example.com",
                status="complete",
                name="Rival Co",
                unique_value_prop="Cheaper, but slower support.",
            )
        )
        await session.commit()

    update = await graph_module._gather_context_node(
        {
            "company_id": company_id,
            "period_days": 7,
            "context": "",
            "generated": None,
            "status": "pending",
            "status_error": None,
        }
    )

    assert "Spring Launch" in update["context"]
    assert "Drive signups for the new product line." in update["context"]
    assert "Rival Co" in update["context"]
    assert "Cheaper, but slower support." in update["context"]


async def test_gather_context_excludes_campaigns_without_objective(monkeypatch, test_session_factory):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        session.add(
            Campaign(id=uuid.uuid4(), company_id=company_id, status="pending", name="Draft Campaign")
        )
        await session.commit()

    update = await graph_module._gather_context_node(
        {
            "company_id": company_id,
            "period_days": 7,
            "context": "",
            "generated": None,
            "status": "pending",
            "status_error": None,
        }
    )

    assert "Draft Campaign" not in update["context"]
    assert "None available — no past campaigns" in update["context"]


async def test_gather_context_only_includes_trends_within_the_period(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    company_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete", name="Acme"))
        session.add(
            Trend(
                id=uuid.uuid4(),
                source="rss",
                title="Recent relevant trend",
                url="https://example.com/a",
                relevance_score=0.8,
                raw_metadata={},
                discovered_at=now - timedelta(days=1),
            )
        )
        session.add(
            Trend(
                id=uuid.uuid4(),
                source="rss",
                title="Stale trend from a month ago",
                url="https://example.com/b",
                relevance_score=0.9,
                raw_metadata={},
                discovered_at=now - timedelta(days=30),
            )
        )
        await session.commit()

    update = await graph_module._gather_context_node(
        {"company_id": company_id, "period_days": 7, "context": "", "generated": None, "status": "pending", "status_error": None}
    )

    assert "Recent relevant trend" in update["context"]
    assert "Stale trend from a month ago" not in update["context"]


async def test_run_trend_report_generation_marks_failed_on_generation_failure(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_trend_report", _stub_generate_trend_report_failed)

    company_id = uuid.uuid4()
    report_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_id, url="https://example.com", status="complete"))
        session.add(TrendReport(id=report_id, company_id=company_id, status="pending", period_days=7))
        await session.commit()

    await graph_module.run_trend_report_generation(report_id, company_id, 7)

    async with test_session_factory() as session:
        report = await session.get(TrendReport, report_id)

    assert report.status == "failed"
    assert report.status_error is not None


async def test_run_scheduled_daily_reports_only_processes_complete_companies(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_trend_report", _stub_generate_trend_report)

    complete_id = uuid.uuid4()
    pending_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=complete_id, url="https://complete.example.com", status="complete"))
        session.add(Company(id=pending_id, url="https://pending.example.com", status="pending"))
        await session.commit()

    await graph_module.run_scheduled_daily_reports()

    async with test_session_factory() as session:
        reports = (
            await session.execute(select(TrendReport))
        ).scalars().all()

    assert len(reports) == 1
    assert reports[0].company_id == complete_id
    assert reports[0].period_days == 1
    assert reports[0].status == "complete"


async def test_run_scheduled_daily_reports_isolates_per_company_failures(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)

    processed = []

    async def _flaky_run_trend_report_generation(report_id, company_id, period_days):
        processed.append(company_id)
        raise RuntimeError("boom")

    monkeypatch.setattr(
        graph_module, "run_trend_report_generation", _flaky_run_trend_report_generation
    )

    company_a = uuid.uuid4()
    company_b = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(Company(id=company_a, url="https://a.example.com", status="complete"))
        session.add(Company(id=company_b, url="https://b.example.com", status="complete"))
        await session.commit()

    # Should not raise even though every company's generation call fails.
    await graph_module.run_scheduled_daily_reports()

    assert set(processed) == {company_a, company_b}


async def test_run_trend_report_generation_marks_failed_when_company_missing(
    monkeypatch, test_session_factory
):
    monkeypatch.setattr(graph_module, "async_session_factory", test_session_factory)
    monkeypatch.setattr(graph_module, "generate_trend_report", _stub_generate_trend_report)

    report_id = uuid.uuid4()
    missing_company_id = uuid.uuid4()
    async with test_session_factory() as session:
        session.add(TrendReport(id=report_id, company_id=missing_company_id, status="pending", period_days=7))
        await session.commit()

    await graph_module.run_trend_report_generation(report_id, missing_company_id, 7)

    async with test_session_factory() as session:
        report = await session.get(TrendReport, report_id)

    assert report.status == "failed"
    assert report.status_error == "Company not found"
