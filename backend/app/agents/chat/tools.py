"""Tools the chat agent can call.

`TOOL_SCHEMAS`/`TOOL_IMPLEMENTATIONS` below are strictly read-only — no
INSERT/UPDATE/DELETE — and are executed automatically inside `agent.py`'s
tool loop. `WRITE_TOOL_SCHEMAS`/`WRITE_TOOL_IMPLEMENTATIONS` at the bottom
are the opposite: real mutations (approve/reject/regenerate/create), which
is exactly why `agent.py` never executes them itself. Claude seeing a write
tool ends the turn with a proposal instead, and these implementations only
ever run from the `/confirm-action` endpoint once a human has approved
them. Each function still returns a plain string (the `tool_result` content
Claude sees, or the confirmation-result text) and never raises — an invalid
argument or a missing row becomes a descriptive string, not a crash.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.content_management.content_plan_graph import (
    regenerate_item_draft_copy,
    run_content_plan_generation,
)
from app.agents.knowledge_base.generated_content_indexing import index_on_approval
from app.agents.knowledge_base.search import similarity_search
from app.agents.trend_analyzer.relevance import fetch_scored_trends
from app.config import settings
from app.db.models import Campaign, Company, ContentItem, ContentPlan, Strategy

TOOL_SCHEMAS = [
    {
        "name": "list_trending_topics",
        "description": (
            "List currently trending topics that are highly relevant and recently "
            "discovered. Use this when the user asks what's trending, what's "
            "happening, or for content ideas grounded in current trends."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max number of trends to return (default 10).",
                },
            },
        },
    },
    {
        "name": "get_company_summary",
        "description": (
            "Get a company's onboarded profile — industry, business model, target "
            "audience, brand voice, and summary. Use this when the user asks about "
            "a specific client/company by name or id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": "string",
                    "description": "The company's UUID.",
                },
            },
            "required": ["company_id"],
        },
    },
    {
        "name": "search_knowledge_base",
        "description": (
            "Semantic search over a company's knowledge base — scraped website "
            "content, uploaded documents, blog posts, AND the company's own "
            "approved content (past approved captions and strategies). Use this "
            "to answer questions about what a company's own site/documents say, "
            "or what they've posted/approved before (e.g. \"what have we posted "
            "about X\" or \"what's our approved strategy for Y\")."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for."},
                "company_id": {
                    "type": "string",
                    "description": "Restrict the search to one company's documents (optional).",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_content_pipeline_status",
        "description": (
            "Get counts of a company's strategies, content plans, and campaigns by "
            "status (pending/complete/failed, approval status). Use this when the "
            "user asks what's in progress or what's ready for review for a client."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": "string",
                    "description": "The company's UUID.",
                },
            },
            "required": ["company_id"],
        },
    },
]


def _parse_uuid(value: str, label: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None


async def list_trending_topics(
    session: AsyncSession, *, company_id: str | None = None, limit: int | None = None
) -> str:
    """`company_id` isn't in this tool's JSON schema — the dispatcher injects
    the conversation's own company (see `_execute_tool`), so a
    company-scoped chat ranks trends by that company's relevance rather
    than the legacy global score. Conversations with no company still work
    and fall back to the global ranking.

    Uses `fetch_scored_trends` rather than `get_recommended_trends` so the
    relevance number shown is the same one the ranking used — printing
    `Trend.relevance_score` next to a per-company ordering would quietly
    report a different company's score."""
    scored = await fetch_scored_trends(
        session,
        _parse_uuid(company_id, "company_id") if company_id else None,
        limit=limit or 10,
        min_score=settings.TREND_RECOMMENDATION_MIN_RELEVANCE,
        max_age_days=settings.TREND_RECOMMENDATION_MAX_AGE_DAYS,
    )
    if not scored:
        return "No trending topics meet the recommendation bar right now."
    lines = [
        f"- {trend.title} (source: {trend.source}, relevance: {score:.2f})"
        for trend, score in scored
    ]
    return "Trending topics:\n" + "\n".join(lines)


async def get_company_summary(session: AsyncSession, *, company_id: str) -> str:
    parsed = _parse_uuid(company_id, "company_id")
    if parsed is None:
        return f"'{company_id}' isn't a valid company id."
    company = await session.get(Company, parsed)
    if company is None:
        return f"No company found with id {company_id}."
    if company.status not in ("complete", "complete_no_profile"):
        return f"{company.url} — onboarding not finished yet (status: {company.status})."

    fields = [
        f"Name: {company.name or company.url}",
        f"Industry: {company.industry or 'unknown'}",
        f"Business model: {company.business_model or 'unknown'}",
        f"Target audience: {company.target_audience or 'unknown'}",
        f"Brand voice: {company.brand_voice or 'unknown'}",
        f"Summary: {company.summary or 'unknown'}",
    ]
    return "\n".join(fields)


async def search_knowledge_base(
    session: AsyncSession, *, query: str, company_id: str | None = None
) -> str:
    parsed_company_id = None
    if company_id is not None:
        parsed_company_id = _parse_uuid(company_id, "company_id")
        if parsed_company_id is None:
            return f"'{company_id}' isn't a valid company id."

    hits = await similarity_search(session, query, company_id=parsed_company_id, k=5)
    if not hits:
        return "No matching knowledge base content found."
    lines = [f"- ({hit.source_type}, {hit.source_url}): {hit.content[:400]}" for hit in hits]
    return "Knowledge base search results:\n" + "\n".join(lines)


async def get_content_pipeline_status(session: AsyncSession, *, company_id: str) -> str:
    parsed = _parse_uuid(company_id, "company_id")
    if parsed is None:
        return f"'{company_id}' isn't a valid company id."
    company = await session.get(Company, parsed)
    if company is None:
        return f"No company found with id {company_id}."

    strategy_count = (
        await session.execute(
            select(func.count()).select_from(Strategy).where(Strategy.company_id == parsed)
        )
    ).scalar_one()
    pending_strategy_approvals = (
        await session.execute(
            select(func.count())
            .select_from(Strategy)
            .where(Strategy.company_id == parsed, Strategy.approval_status == "pending")
        )
    ).scalar_one()
    content_plan_count = (
        await session.execute(
            select(func.count()).select_from(ContentPlan).where(ContentPlan.company_id == parsed)
        )
    ).scalar_one()
    campaign_count = (
        await session.execute(
            select(func.count()).select_from(Campaign).where(Campaign.company_id == parsed)
        )
    ).scalar_one()

    return (
        f"{company.name or company.url}: {strategy_count} strategies "
        f"({pending_strategy_approvals} pending approval), {content_plan_count} content plans, "
        f"{campaign_count} campaigns."
    )


TOOL_IMPLEMENTATIONS = {
    "list_trending_topics": list_trending_topics,
    "get_company_summary": get_company_summary,
    "search_knowledge_base": search_knowledge_base,
    "get_content_pipeline_status": get_content_pipeline_status,
}


WRITE_TOOL_SCHEMAS = [
    {
        "name": "approve_content_item",
        "description": (
            "Approve a content item so it's ready to publish. This is a real "
            "action — only call it when the user has clearly asked to approve "
            "a specific item."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content_item_id": {"type": "string", "description": "The content item's UUID."},
            },
            "required": ["content_item_id"],
        },
    },
    {
        "name": "reject_content_item",
        "description": (
            "Reject a content item, taking it out of the publishing queue. "
            "Only call it when the user has clearly asked to reject a "
            "specific item."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content_item_id": {"type": "string", "description": "The content item's UUID."},
            },
            "required": ["content_item_id"],
        },
    },
    {
        "name": "regenerate_content_item_draft",
        "description": (
            "Rewrite a content item's draft copy with a fresh AI generation, "
            "replacing the current draft (the old one is kept in its "
            "revision history). Only call it when the user has clearly asked "
            "to regenerate a specific item's draft."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content_item_id": {"type": "string", "description": "The content item's UUID."},
            },
            "required": ["content_item_id"],
        },
    },
    {
        "name": "create_content_plan",
        "description": (
            "Generate a brand-new content calendar (a set of content items) "
            "for a company. Only call it when the user has clearly asked to "
            "create or generate a new content plan/calendar for a specific "
            "company."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_id": {"type": "string", "description": "The company's UUID."},
                "days": {
                    "type": "integer",
                    "description": "Number of days the plan should cover (optional).",
                },
            },
            "required": ["company_id"],
        },
    },
]


async def approve_content_item(session: AsyncSession, *, content_item_id: str) -> str:
    parsed = _parse_uuid(content_item_id, "content_item_id")
    if parsed is None:
        return f"'{content_item_id}' isn't a valid content item id."
    item = await session.get(ContentItem, parsed)
    if item is None:
        return f"No content item found with id {content_item_id}."

    item.approval_status = "approved"
    item.approved_by = "LoomVerse AI chat"

    content_plan = await session.get(ContentPlan, item.content_plan_id)
    if content_plan is not None:
        await index_on_approval(
            session,
            content_plan.company_id,
            "content_item",
            f"content-item://{item.id}",
            item.draft_copy or item.description,
        )

    await session.commit()
    return f"Approved content item '{item.title}'."


async def reject_content_item(session: AsyncSession, *, content_item_id: str) -> str:
    parsed = _parse_uuid(content_item_id, "content_item_id")
    if parsed is None:
        return f"'{content_item_id}' isn't a valid content item id."
    item = await session.get(ContentItem, parsed)
    if item is None:
        return f"No content item found with id {content_item_id}."

    item.approval_status = "rejected"
    await session.commit()
    return f"Rejected content item '{item.title}'."


async def regenerate_content_item_draft(session: AsyncSession, *, content_item_id: str) -> str:
    parsed = _parse_uuid(content_item_id, "content_item_id")
    if parsed is None:
        return f"'{content_item_id}' isn't a valid content item id."

    # Manages its own session (see content_plan_graph.py) — the session
    # passed to this function is unused, kept only so every write tool has
    # the same (session, **kwargs) shape the confirm-action endpoint calls.
    item, ok = await regenerate_item_draft_copy(parsed)
    if item is None:
        return f"No content item found with id {content_item_id}."
    if not ok:
        return f"Regeneration failed for '{item.title}' (Claude API unavailable)."
    return f"Regenerated draft for '{item.title}'."


async def create_content_plan(
    session: AsyncSession, *, company_id: str, days: int | None = None
) -> str:
    parsed = _parse_uuid(company_id, "company_id")
    if parsed is None:
        return f"'{company_id}' isn't a valid company id."
    company = await session.get(Company, parsed)
    if company is None:
        return f"No company found with id {company_id}."

    content_plan = ContentPlan(id=uuid.uuid4(), company_id=parsed, status="pending")
    session.add(content_plan)
    await session.commit()

    await run_content_plan_generation(content_plan.id, parsed, None, days)
    return f"Started generating a new content plan for {company.name or company.url}."


WRITE_TOOL_IMPLEMENTATIONS = {
    "approve_content_item": approve_content_item,
    "reject_content_item": reject_content_item,
    "regenerate_content_item_draft": regenerate_content_item_draft,
    "create_content_plan": create_content_plan,
}
