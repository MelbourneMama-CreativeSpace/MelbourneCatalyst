"""Tools the chat agent can call.

`TOOL_SCHEMAS`/`TOOL_IMPLEMENTATIONS` below are strictly read-only — no
INSERT/UPDATE/DELETE — and are executed automatically inside `agent.py`'s
tool loop. `WRITE_TOOL_SCHEMAS`/`WRITE_TOOL_IMPLEMENTATIONS` at the bottom
are the opposite: real mutations (approve/reject/regenerate/publish/
schedule/create-a-plan), which is exactly why `agent.py` never executes
them itself. Claude seeing a write tool ends the turn with a proposal
instead, and these implementations only ever run from the
`/confirm-action` endpoint once a human has approved them — which also
re-checks access against the actual target (`_ensure_action_target_allowed`
in chat.py), so none of the functions below need a `current_user`
parameter of their own; by the time one runs, access is already settled.

Most implementations return a plain string (the `tool_result` content
Claude sees, or the confirmation-result text) and never raise — an invalid
argument or a missing row becomes a descriptive string, not a crash. A few
read tools (`list_trending_topics`, `find_content_items`,
`create_content_item`) instead return `tuple[str, list[dict]]` — the
second element is zero or more "cards": small structured snapshots (a
content item, a trend) the frontend renders as flashcards instead of the
assistant only ever describing things in prose.

`create_content_item` (write ONE post right now) is deliberately a read
tool, not a write one, even though it's an INSERT: generating a draft has
no real-world consequence (nothing external happens, nothing is posted —
it's a `pending`, fully editable/deletable row, exactly like the old
manual-item form never needed confirmation either). The write boundary
here is publishing/scheduling — `publish_content_item` and
`schedule_content_item` below — which do.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.content_management.content_plan_graph import (
    create_manual_item,
    regenerate_item_draft_copy,
    run_content_plan_generation,
)
from app.agents.knowledge_base.generated_content_indexing import index_on_approval
from app.agents.knowledge_base.search import similarity_search
from app.agents.social_media_analyzer.publish import publish_post
from app.agents.trend_analyzer.relevance import fetch_scored_trends
from app.config import settings
from app.db.models import (
    Campaign,
    Company,
    ContentItem,
    ContentPlan,
    PlatformConnection,
    PublishAttempt,
    Strategy,
    Trend,
)


def _content_item_card(item: ContentItem, company_id: uuid.UUID) -> dict:
    return {
        "type": "content_item",
        "id": str(item.id),
        "company_id": str(company_id),
        "title": item.title,
        "platform": item.platform,
        "content_type": item.content_type,
        "draft_copy": item.draft_copy,
        "hashtags": item.hashtags,
        "approval_status": item.approval_status,
        "scheduled_at": item.scheduled_at.isoformat() if item.scheduled_at else None,
        "published_at": item.published_at.isoformat() if item.published_at else None,
    }


def _trend_card(trend: Trend) -> dict:
    return {
        "type": "trend",
        "id": str(trend.id),
        "title": trend.title,
        "source": trend.source,
        "url": trend.url,
        "category": trend.category,
        "insight": trend.insight,
        "relevance_score": trend.relevance_score,
    }


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
    {
        "name": "find_content_items",
        "description": (
            "Look up existing content items (drafts, scheduled, or published "
            "posts) for a company — by a text search over their title, and/or "
            "filtered by platform. Use this whenever the user refers to a post "
            "they've already created, asks what's in the pipeline, or asks to "
            "see something specific, so it can be shown to them directly rather "
            "than described in words."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_id": {"type": "string", "description": "The company's UUID."},
                "query": {
                    "type": "string",
                    "description": "Text to search for in the title (optional).",
                },
                "platform": {
                    "type": "string",
                    "enum": ["instagram", "linkedin", "twitter", "tiktok", "youtube", "blog", "facebook", "threads"],
                    "description": "Restrict to one platform (optional).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 5, max 10).",
                },
            },
            "required": ["company_id"],
        },
    },
    {
        "name": "create_content_item",
        "description": (
            "Write ONE ready-to-publish post right now — the single-post "
            "counterpart to create_content_plan (which builds a whole "
            "calendar of several). Use this once you have enough to go on: "
            "what it's about and, ideally, which platform. If the user's "
            "request is vague (no topic, or content that clearly wants a "
            "photo/video they haven't attached), ask a clarifying question "
            "first instead of guessing — don't call this speculatively. Any "
            "attached file appears in the conversation as a markdown link/ "
            "image; include it verbatim in `topic` so it's part of the "
            "brief. The result is shown to the user as a card with its own "
            "Post/Schedule actions — you don't need to ask them what to do "
            "with it next."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_id": {"type": "string", "description": "The company's UUID."},
                "topic": {
                    "type": "string",
                    "description": (
                        "What the post should be about, in the user's own words — "
                        "their brief, including any attached media markdown."
                    ),
                },
                "platform": {
                    "type": "string",
                    "enum": ["instagram", "linkedin", "twitter", "tiktok", "youtube", "blog", "facebook", "threads"],
                    "description": "Infer from what the user said; default to linkedin if genuinely unclear.",
                },
                "content_type": {
                    "type": "string",
                    "enum": ["post", "video", "article", "carousel", "story", "newsletter", "podcast"],
                    "description": "Infer from what the user said; default to post if genuinely unclear.",
                },
            },
            "required": ["company_id", "topic"],
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
) -> tuple[str, list[dict]]:
    """`company_id` isn't in this tool's JSON schema — the dispatcher injects
    the conversation's own company (see `_execute_tool`), so a
    company-scoped chat ranks trends by that company's relevance rather
    than the legacy global score. Conversations with no company still work
    and fall back to the global ranking.

    Uses `fetch_scored_trends` rather than the plain recommendation list so
    the relevance number shown is the same one the ranking used — printing
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
        return "No trending topics meet the recommendation bar right now.", []
    lines = [
        f"- {trend.title} (source: {trend.source}, relevance: {score:.2f})"
        for trend, score in scored
    ]
    text = "Trending topics:\n" + "\n".join(lines)
    return text, [_trend_card(trend) for trend, _score in scored]


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


async def find_content_items(
    session: AsyncSession,
    *,
    company_id: str,
    query: str | None = None,
    platform: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[dict]]:
    parsed = _parse_uuid(company_id, "company_id")
    if parsed is None:
        return f"'{company_id}' isn't a valid company id.", []

    stmt = (
        select(ContentItem, ContentPlan.company_id)
        .join(ContentPlan, ContentItem.content_plan_id == ContentPlan.id)
        .where(ContentPlan.company_id == parsed)
        .order_by(ContentItem.created_at.desc())
        .limit(min(limit or 5, 10))
    )
    if platform:
        stmt = stmt.where(ContentItem.platform == platform)
    if query:
        stmt = stmt.where(ContentItem.title.ilike(f"%{query}%"))

    rows = (await session.execute(stmt)).all()
    if not rows:
        return "No matching content items found.", []

    summary = "; ".join(f"{item.title} ({item.platform}, {item.approval_status})" for item, _ in rows)
    return f"Found {len(rows)} matching item(s): {summary}", [
        _content_item_card(item, item_company_id) for item, item_company_id in rows
    ]


async def create_content_item(
    session: AsyncSession,
    *,
    company_id: str,
    topic: str,
    platform: str | None = None,
    content_type: str | None = None,
) -> tuple[str, list[dict]]:
    parsed = _parse_uuid(company_id, "company_id")
    if parsed is None:
        return f"'{company_id}' isn't a valid company id.", []
    company = await session.get(Company, parsed)
    if company is None:
        return f"No company found with id {company_id}.", []
    if company.status != "complete":
        return (
            f"{company.name or company.url}'s profile isn't ready yet — finish onboarding "
            "before generating content.",
            [],
        )

    item, ok = await create_manual_item(parsed, topic, platform or "linkedin", content_type or "post")
    if not ok or item is None:
        return "Content generation failed (check ANTHROPIC_API_KEY / Claude API availability).", []
    text = f"Created \"{item.title}\" — a {item.platform} {item.content_type} draft, ready to review."
    return text, [_content_item_card(item, parsed)]


TOOL_IMPLEMENTATIONS = {
    "list_trending_topics": list_trending_topics,
    "get_company_summary": get_company_summary,
    "search_knowledge_base": search_knowledge_base,
    "get_content_pipeline_status": get_content_pipeline_status,
    "find_content_items": find_content_items,
    "create_content_item": create_content_item,
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
    {
        "name": "publish_content_item",
        "description": (
            "Publish a content item to its platform right now, using the "
            "company's connected account. A real, irreversible action — "
            "only call it when the user has clearly confirmed they want it "
            "posted now (e.g. \"post it\", \"publish that\"), whether that's "
            "in reply to you asking or as their original request."
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
        "name": "schedule_content_item",
        "description": (
            "Schedule a content item to publish automatically at a future "
            "time. Only call it when the user has given (or clearly "
            "confirmed) a specific date/time to schedule for."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content_item_id": {"type": "string", "description": "The content item's UUID."},
                "scheduled_at": {
                    "type": "string",
                    "description": "ISO 8601 date-time to schedule for, e.g. 2026-08-10T09:00:00Z.",
                },
            },
            "required": ["content_item_id", "scheduled_at"],
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


async def publish_content_item(session: AsyncSession, *, content_item_id: str) -> str:
    parsed = _parse_uuid(content_item_id, "content_item_id")
    if parsed is None:
        return f"'{content_item_id}' isn't a valid content item id."
    item = await session.get(ContentItem, parsed)
    if item is None:
        return f"No content item found with id {content_item_id}."
    content_plan = await session.get(ContentPlan, item.content_plan_id)
    if content_plan is None:
        return f"No content item found with id {content_item_id}."
    if item.published_at is not None:
        return f"'{item.title}' has already been published."
    if not item.draft_copy:
        return f"'{item.title}' has no draft copy yet."

    connection = (
        await session.execute(
            select(PlatformConnection).where(
                PlatformConnection.company_id == content_plan.company_id,
                PlatformConnection.platform == item.platform,
            )
        )
    ).scalar_one_or_none()
    if connection is None or connection.status != "connected" or connection.composio_connected_account_id is None:
        return (
            f"{item.platform} isn't connected for this company yet — connect it from "
            "Integrations first."
        )

    try:
        execution_id = await publish_post(
            connection.platform, connection.composio_connected_account_id, item.draft_copy
        )
    except Exception as exc:
        error_message = str(exc)[:512]
        session.add(
            PublishAttempt(
                id=uuid.uuid4(),
                content_item_id=item.id,
                platform_connection_id=connection.id,
                status="failed",
                status_error=error_message,
            )
        )
        await session.commit()
        return f"Publishing '{item.title}' failed: {error_message[:200]}"

    item.published_at = datetime.now(timezone.utc)
    session.add(
        PublishAttempt(
            id=uuid.uuid4(),
            content_item_id=item.id,
            platform_connection_id=connection.id,
            status="success",
            composio_execution_id=execution_id,
        )
    )
    await session.commit()
    return f"Published '{item.title}' to {item.platform}."


async def schedule_content_item(
    session: AsyncSession, *, content_item_id: str, scheduled_at: str
) -> str:
    parsed = _parse_uuid(content_item_id, "content_item_id")
    if parsed is None:
        return f"'{content_item_id}' isn't a valid content item id."
    item = await session.get(ContentItem, parsed)
    if item is None:
        return f"No content item found with id {content_item_id}."
    if item.published_at is not None:
        return f"'{item.title}' has already been published."

    try:
        when = datetime.fromisoformat(scheduled_at)
    except ValueError:
        return (
            f"'{scheduled_at}' isn't a valid date/time (use ISO format, e.g. "
            "2026-08-10T09:00:00)."
        )

    item.scheduled_at = when
    await session.commit()
    return f"Scheduled '{item.title}' for {when.isoformat()}."


WRITE_TOOL_IMPLEMENTATIONS = {
    "approve_content_item": approve_content_item,
    "reject_content_item": reject_content_item,
    "regenerate_content_item_draft": regenerate_content_item_draft,
    "create_content_plan": create_content_plan,
    "publish_content_item": publish_content_item,
    "schedule_content_item": schedule_content_item,
}
