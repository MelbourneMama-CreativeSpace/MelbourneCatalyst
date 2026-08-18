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

import re
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
from app.agents.knowledge_base.ingestion import ingest_raw_document
from app.agents.knowledge_base.schemas import RawDocument
from app.agents.knowledge_base.search import similarity_search
from app.agents.social_media_analyzer import profile_lookup
from app.agents.social_media_analyzer.publish import (
    DeleteNotSupportedError,
    delete_post,
    get_post_url,
    publish_post,
)
from app.agents.social_media_analyzer.youtube_upload import (
    delete_youtube_video,
    enqueue_youtube_upload,
    fetch_video_analytics,
    get_video_url,
)
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
    YouTubeUploadJob,
)
from app.security.auth import CurrentUser
from app.security.ownership import accessible_company_clause


def _content_item_card(
    item: ContentItem, company_id: uuid.UUID, *, card_context: str = "preview"
) -> dict:
    """`card_context` tells the frontend why this card is showing up, since
    the same item can be shown for very different reasons:

    - "preview" (the default) — just surfacing a draft that was created or
      found. No publish/schedule controls: the user hasn't asked to post
      anything, so a card that appeared because they said "write me a
      post" has no business offering a one-click Publish button.
    - "action" — this card is the preview attached to an actual
      publish/schedule/approve/reject/regenerate/delete *proposal* (see
      `_preview_card_for_write_tool` in agent.py), i.e. the user's own
      request already implies posting/scheduling. Only here does the
      frontend render publish/schedule controls."""
    return {
        "type": "content_item",
        "id": str(item.id),
        "company_id": str(company_id),
        "title": item.title,
        "platform": item.platform,
        "content_type": item.content_type,
        "draft_copy": item.draft_copy,
        "hashtags": item.hashtags,
        "media_url": item.media_url,
        "approval_status": item.approval_status,
        "scheduled_at": item.scheduled_at.isoformat() if item.scheduled_at else None,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "card_context": card_context,
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
        "name": "list_companies",
        "description": (
            "List all companies the user has onboarded, with their names, IDs, "
            "and status. Use this to resolve a company name to its UUID before "
            "calling other tools that need a company_id, or when the user asks "
            "what companies or clients are in the system."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "list_trending_topics",
        "description": (
            "List the company's best available trending topics, ranked by relevance "
            "— always returns whatever exists, even if nothing clears the 'strongly "
            "relevant' bar, so there's always real trend context to reference. Each "
            "result's relevance score says how strong the match actually is; treat "
            "anything below ~0.5 as weak and say so plainly rather than presenting it "
            "as a genuine trend. Use this when the user asks what's trending, what's "
            "happening, or wants content grounded in current trends — and also before "
            "writing content the user wants tied to 'the trends' in general, so you "
            "have real ids/insights to reference instead of inventing one."
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
            "a specific client/company by name or id. company_id is OPTIONAL — omit "
            "it to use the one company on the account (or ask which one, if there's "
            "more than one). Never ask the user for a UUID directly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": "string",
                    "description": "The company's UUID — OPTIONAL, resolved automatically if omitted.",
                },
            },
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
        "name": "save_to_knowledge_base",
        "description": (
            "Save something the user shared in this conversation directly to the "
            "company's knowledge base — a stated requirement, a decision, a "
            "brand/style preference, a fact about their business or customers — "
            "so it's searchable (via search_knowledge_base) and usable as real "
            "context for every future conversation and piece of content, not just "
            "remembered for this one turn. Use this when something reads as a "
            "standing fact worth keeping, not routine back-and-forth — a person "
            "explaining what their product does, a stated audience/tone "
            "preference, a real customer quote they typed out, a decision they "
            "made. Don't use it for small talk or anything already covered by the "
            "company's own onboarded profile. Always tell the user in your reply "
            "that you saved it — never do this silently."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "A short, descriptive title for this piece of knowledge.",
                },
                "content": {
                    "type": "string",
                    "description": "The actual content to save — the user's own words/facts, not a summary.",
                },
                "company_id": {
                    "type": "string",
                    "description": "The company's UUID — OPTIONAL, resolved automatically if omitted.",
                },
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "get_content_pipeline_status",
        "description": (
            "Get counts of a company's strategies, content plans, and campaigns by "
            "status (pending/complete/failed, approval status). Use this when the "
            "user asks what's in progress or what's ready for review for a client. "
            "company_id is OPTIONAL — omit it to use the one company on the account "
            "(or ask which one, if there's more than one). Never ask the user for a "
            "UUID directly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": "string",
                    "description": "The company's UUID — OPTIONAL, resolved automatically if omitted.",
                },
            },
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
            "than described in words. company_id is OPTIONAL — omit it to use "
            "the one company on the account (or ask which one, if there's more "
            "than one). Never ask the user for a UUID directly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": "string",
                    "description": "The company's UUID — OPTIONAL, resolved automatically if omitted.",
                },
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
        },
    },
    {
        "name": "create_content_item",
        "description": (
            "Write ONE ready-to-publish post right now — the single-post "
            "counterpart to create_content_plan (which builds a whole "
            "calendar of several). Use this once you have enough to go on: "
            "what it's about and, ideally, which platform. "
            "company_id is OPTIONAL — only include it if the user has "
            "specifically mentioned a company or client by name (resolve "
            "the name to a UUID with list_companies first). If no company "
            "is mentioned, write a high-quality generic post without one. "
            "Never ask the user for a company UUID — resolve it yourself "
            "or omit it. "
            "Every post already gets the company's own currently-relevant "
            "trends as ambient context automatically — you don't need to "
            "restate them. If the user is asking for content built around "
            "one SPECIFIC trend they saw from list_trending_topics (e.g. "
            "\"write something about that YC one\", \"make a post out of "
            "the top trend\"), pass its real id as trend_id — always quote "
            "the id verbatim from list_trending_topics' own result text "
            "(never invent one), the same rule as content_item_id "
            "elsewhere. This guarantees that trend is actually the center "
            "of the post rather than just background noise, and properly "
            "links the resulting item back to it. "
            "If the user's request is vague (no topic at all), ask a "
            "clarifying question first instead of guessing. Any attached "
            "file appears in the conversation as a markdown link/image; "
            "include it verbatim in `topic`. The result is shown to the "
            "user as a card with its own Post/Schedule actions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": "string",
                    "description": (
                        "The company's UUID — OPTIONAL. Only supply this when the user "
                        "has explicitly mentioned a specific company/client. Resolve "
                        "names to UUIDs using list_companies. Never ask the user for "
                        "a UUID directly."
                    ),
                },
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
                "trend_id": {
                    "type": "string",
                    "description": (
                        "OPTIONAL — a specific trend's real UUID from "
                        "list_trending_topics' own result text, when the user wants "
                        "content built around ONE particular trend. Omit for a regular "
                        "post; ambient trend context is already included either way."
                    ),
                },
            },
            "required": ["topic"],
        },
    },
    {
        "name": "get_youtube_video_analytics",
        "description": (
            "Get real view/like/comment counts for a video this app has "
            "already uploaded to YouTube, straight from YouTube's own API. "
            "Use this whenever the user asks how a video is doing, its "
            "views/likes, or its analytics/stats. This is view/like/comment "
            "counts only — NOT full YouTube Studio-grade analytics (no "
            "watch time, audience retention, or traffic sources; no such "
            "data is available through this app). If the user wants that "
            "deeper level, say plainly that only view/like/comment counts "
            "are available here and point them to YouTube Studio directly "
            "for the rest — never fabricate numbers you don't have. `title` "
            "is OPTIONAL — narrows to one video by a substring of what it "
            "was uploaded as (e.g. \"the YC video\", \"birthday wish\"); "
            "omit it to see the most recently uploaded few. company_id is "
            "OPTIONAL — omit it to use the one company on the account."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": "string",
                    "description": "The company's UUID — OPTIONAL, resolved automatically if omitted.",
                },
                "title": {
                    "type": "string",
                    "description": "Substring to match against the video's uploaded title (optional).",
                },
            },
        },
    },
    {
        "name": "analyze_social_profile",
        "description": (
            "Look up a PUBLIC social media profile by username/handle — real "
            "name, bio, follower count, PLUS a handful of the account's actual "
            "recent posts — to understand its real niche, audience, and voice. "
            "The recent posts matter more than the bio for this: a bio says what "
            "an account claims to be about, real posts show what it's actually "
            "posting. Use this whenever the user pastes a username or profile URL "
            "(with or without @) and wants to understand that account or create "
            "content inspired by it; read the bio AND the recent posts yourself "
            "to work out the real niche/themes/style, then use create_content_item "
            "for the actual post once asked. Only twitter, youtube, and facebook "
            "genuinely support looking up an ARBITRARY public account this way — "
            "instagram, linkedin, and tiktok's own APIs only allow querying an "
            "account you already manage, not any public one by username, "
            "confirmed live against each platform's real capability. Calling this "
            "for one of those three (or any lookup that fails — no connection, "
            "account not found) returns a clear explanation AND a prompt to ask "
            "the user for a manual description instead — a person's own words "
            "about what an account posts about are a completely valid substitute "
            "for a fetched profile, and create_content_item's topic already "
            "accepts free-form context like that directly. Never fabricate a bio, "
            "niche, or posts to fill the gap yourself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["twitter", "youtube", "facebook", "instagram", "linkedin", "tiktok"],
                    "description": "Which platform the username/handle belongs to.",
                },
                "username": {
                    "type": "string",
                    "description": (
                        "The handle/username (with or without @) or a full profile URL, "
                        "exactly as pasted."
                    ),
                },
                "company_id": {
                    "type": "string",
                    "description": (
                        "The company's UUID — OPTIONAL, resolved automatically if omitted. "
                        "Needed because even a public lookup runs through that company's own "
                        "connected account for the platform."
                    ),
                },
            },
            "required": ["platform", "username"],
        },
    },
]


def _parse_uuid(value: str, label: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None


# Matches the exact markdown an image attachment is appended to a message
# as (see frontend chat-panel.tsx's handleSend / chat-attachments.ts):
# `![filename](url)` — the leading `!` is what marks it an image rather
# than a generic file attachment (`[filename](url)`), so this only ever
# matches a real image, not any attachment.
_IMAGE_MARKDOWN_PATTERN = re.compile(r"!\[[^\]]*\]\((https?://[^\s)]+)\)")


def _extract_first_image_url(text: str) -> str | None:
    """The first attached image's URL already present in `text`, if any —
    lets a new content item pick up an image the user already attached in
    chat automatically, rather than requiring it be re-uploaded through a
    separate step once the draft exists."""
    match = _IMAGE_MARKDOWN_PATTERN.search(text)
    return match.group(1) if match else None


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
    report a different company's score.

    Deliberately unfiltered (no min_score/max_age_days), unlike
    `get_recommended_trends`'s dashboard-facing "genuinely great, don't
    show anything weaker" bar. This tool feeds the conversation, not a UI
    badge: a niche with no trend clearing that bar this week isn't a niche
    with *zero* real trend context, and this used to hand Claude an empty
    list either way — indistinguishable from "trend collection hasn't run
    yet" — which meant every piece of content built from it silently
    dropped trend grounding instead of citing the closest real match with
    an honest confidence caveat. The relevance score is still printed per
    trend precisely so Claude (and, downstream, the user) can tell a 0.81
    match from a 0.12 one instead of both reading as unqualified "trending."
    """
    scored = await fetch_scored_trends(
        session,
        _parse_uuid(company_id, "company_id") if company_id else None,
        limit=limit or 10,
    )
    if not scored:
        return "No trending topics have been discovered yet — trend collection may not have run for this company's niche.", []
    # `id` has to be in the text Claude actually reads, not just the card
    # data — cards are a UI-only side-channel never fed back into the
    # model's context. Without it here, "write a post about the second
    # one" has no real trend id to pass to create_content_item's
    # trend_id, the same "Invalid content item id" class of bug already
    # fixed for find_content_items/create_content_item. `insight`
    # (why it matters) is included too — the actual substance worth
    # writing content around, not just a bare title.
    lines = [
        f"- {trend.title} (source: {trend.source}, relevance: {score:.2f}, id: {trend.id})"
        + (f" — {trend.insight}" if trend.insight else "")
        for trend, score in scored
    ]
    text = "Trending topics:\n" + "\n".join(lines)
    return text, [_trend_card(trend) for trend, _score in scored]


async def _resolve_company_id(
    session: AsyncSession, user: CurrentUser, company_id: str | None
) -> tuple[uuid.UUID | None, str | None]:
    """Resolve a tool's `company_id`, tolerating the case where Claude's
    tool call omits it even though the JSON schema marks it "required" —
    `tool_choice: auto` doesn't hard-enforce that, so any tool written
    assuming Claude always supplies one crashes exactly the way
    `create_content_item` and `find_content_items` both did in practice.
    Returns `(uuid, None)` on success, or `(None, message)` with a message
    ready to hand straight back to Claude as the tool result — same
    resolve-to-the-one-accessible-company-or-ask shape as
    `create_content_item`'s own fallback."""
    if company_id:
        parsed = _parse_uuid(company_id, "company_id")
        if parsed is None:
            return None, f"'{company_id}' isn't a valid company id."
        return parsed, None
    companies = await _accessible_complete_companies(session, user)
    if not companies:
        return None, "No onboarded company found — finish onboarding a company first."
    if len(companies) > 1:
        names = ", ".join(f"{c.name or c.url} ({c.id})" for c in companies)
        return None, f"Which company did you mean? You have access to: {names}."
    return companies[0].id, None


async def get_company_summary(
    session: AsyncSession, *, user: CurrentUser, company_id: str | None = None
) -> str:
    parsed, error = await _resolve_company_id(session, user, company_id)
    if error:
        return error
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


async def save_to_knowledge_base(
    session: AsyncSession,
    *,
    user: CurrentUser,
    company_id: str | None = None,
    title: str,
    content: str,
) -> str:
    """Saves a real piece of conversational context — a stated
    requirement, decision, preference, or fact the user shared in chat —
    straight to the company's knowledge base, exactly like an uploaded
    document or a manual KB entry would be: chunked, embedded, and
    searchable via search_knowledge_base for every future conversation
    and content generation, not just remembered for this one turn. No
    real-world consequence (nothing external happens, nothing published)
    so this doesn't need confirmation, same reasoning as
    create_content_item — but always tell the user it was saved, in
    plain language, right in the reply; never do this silently."""
    parsed, error = await _resolve_company_id(session, user, company_id)
    if error:
        return error

    raw = RawDocument(
        source_type="chat_insight",
        source_url=f"chat://{uuid.uuid4()}",
        content=content,
        raw_metadata={"title": title},
    )
    chunks_persisted = await ingest_raw_document(session, parsed, raw)
    if chunks_persisted == 0:
        return "Nothing to save — that content was empty."
    await session.commit()
    return f'Saved "{title}" to the knowledge base — searchable for future content from now on.'


async def get_content_pipeline_status(
    session: AsyncSession, *, user: CurrentUser, company_id: str | None = None
) -> str:
    parsed, error = await _resolve_company_id(session, user, company_id)
    if error:
        return error
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
    user: CurrentUser,
    company_id: str | None = None,
    query: str | None = None,
    platform: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[dict]]:
    parsed, error = await _resolve_company_id(session, user, company_id)
    if error:
        return error, []

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

    # `id` has to be in the text Claude actually reads, not just the card
    # data — cards are a UI-only side-channel never fed back into the
    # model's context. Without it here, a follow-up approve/reject/
    # regenerate/publish/schedule call has no real id to quote and either
    # hallucinates one or fails with "Invalid content item id in proposed
    # action" — exactly the bug this fixes.
    summary = "; ".join(
        f"{item.title} ({item.platform}, {item.approval_status}, id: {item.id})" for item, _ in rows
    )
    return f"Found {len(rows)} matching item(s): {summary}", [
        _content_item_card(item, item_company_id) for item, item_company_id in rows
    ]


async def _accessible_complete_companies(session: AsyncSession, user: CurrentUser) -> list[Company]:
    """Every fully-onboarded company `user` can see — the same ownership
    predicate the `/companies` list endpoint uses, so a chat tool can never
    surface a company this person doesn't actually have access to."""
    rows = (
        await session.execute(
            select(Company).where(accessible_company_clause(user), Company.status == "complete")
        )
    ).scalars().all()
    return list(rows)


async def list_companies(session: AsyncSession, *, user: CurrentUser) -> str:
    companies = await _accessible_complete_companies(session, user)
    if not companies:
        return "No companies onboarded yet."
    lines = [f"{c.name or c.url} (id: {c.id})" for c in companies]
    return f"{len(companies)} companies:\n" + "\n".join(lines)


async def create_content_item(
    session: AsyncSession,
    *,
    user: CurrentUser,
    company_id: str | None = None,
    topic: str,
    platform: str | None = None,
    content_type: str | None = None,
    trend_id: str | None = None,
) -> tuple[str, list[dict]]:
    if company_id:
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
    else:
        # No company named — per this tool's own instructions, resolve it
        # rather than ask for a UUID. A `ContentItem` always belongs to a
        # real company (it lives on that company's manual `ContentPlan`),
        # so "a company-less generic post" was never actually something
        # the data model could represent; auto-picking the one company
        # this person has when there's exactly one is the honest version
        # of that promise, not a guess.
        companies = await _accessible_complete_companies(session, user)
        if not companies:
            return (
                "No onboarded company to write this for yet — finish onboarding a company first.",
                [],
            )
        if len(companies) > 1:
            names = ", ".join(f"{c.name or c.url} ({c.id})" for c in companies)
            return (
                f"Which company is this for? You have access to: {names}.",
                [],
            )
        parsed = companies[0].id

    # `topic` carries the user's own words verbatim, attachment markdown
    # included (see this tool's own schema description) — an attached
    # image should land on the new item directly, not require a separate
    # re-upload once the draft already exists.
    media_url = _extract_first_image_url(topic)
    # An invalid/hallucinated trend_id degrades to "no specific trend" —
    # create_manual_item itself already treats an unknown id the same
    # way, so a bad UUID string here isn't worth refusing the whole post
    # over.
    parsed_trend_id = _parse_uuid(trend_id, "trend_id") if trend_id else None
    item, ok = await create_manual_item(
        parsed,
        topic,
        platform or "linkedin",
        content_type or "post",
        media_url=media_url,
        trend_id=parsed_trend_id,
    )
    if not ok or item is None:
        return "Content generation failed (check ANTHROPIC_API_KEY / Claude API availability).", []
    # id included in the text itself (not just the card) so a follow-up
    # approve/reject/regenerate/publish/schedule call in the same
    # conversation has a real id to quote — see find_content_items for the
    # same fix and why it matters.
    text = (
        f"Created \"{item.title}\" (id: {item.id}) — a {item.platform} {item.content_type} "
        "draft, ready to review."
    )
    return text, [_content_item_card(item, parsed)]


async def get_youtube_video_analytics(
    session: AsyncSession,
    *,
    user: CurrentUser,
    company_id: str | None = None,
    title: str | None = None,
) -> str:
    """Real view/like/comment counts for a video this app uploaded to
    YouTube, resolved from this company's own `YouTubeUploadJob` rows (so
    only videos this app actually put up are ever looked up — never an
    arbitrary id Claude might otherwise guess). `title` narrows to one
    upload by substring; omitted, returns the most recent few, letting
    Claude report on whichever the user actually means from the results."""
    parsed, error = await _resolve_company_id(session, user, company_id)
    if error:
        return error

    connection = (
        await session.execute(
            select(PlatformConnection).where(
                PlatformConnection.company_id == parsed,
                PlatformConnection.platform == "youtube",
            )
        )
    ).scalar_one_or_none()
    if connection is None or connection.composio_connected_account_id is None:
        return "YouTube isn't connected for this company yet — connect it from Integrations first."

    stmt = (
        select(YouTubeUploadJob)
        .where(
            YouTubeUploadJob.platform_connection_id == connection.id,
            YouTubeUploadJob.status == "success",
        )
        .order_by(YouTubeUploadJob.created_at.desc())
        .limit(10)
    )
    if title:
        stmt = stmt.where(YouTubeUploadJob.title.ilike(f"%{title}%"))
    jobs = (await session.execute(stmt)).scalars().all()
    if not jobs:
        return (
            f"No successfully uploaded video matching '{title}' found."
            if title
            else "No successfully uploaded YouTube videos found for this company yet."
        )

    video_ids = [j.composio_execution_id for j in jobs if j.composio_execution_id]
    if not video_ids:
        return "Found the upload record, but no YouTube video id was saved for it."

    try:
        items = await fetch_video_analytics(connection, video_ids)
    except Exception as exc:
        return f"Couldn't fetch YouTube analytics: {exc}"
    if not items:
        return "YouTube didn't return statistics for that video (it may have been deleted or made private)."

    lines = []
    for item in items:
        snippet = item.get("snippet") or {}
        stats = item.get("statistics") or {}
        lines.append(
            f"- \"{snippet.get('title', 'Untitled')}\" (video id: {item.get('id')}): "
            f"{stats.get('viewCount', '0')} views, {stats.get('likeCount', '0')} likes, "
            f"{stats.get('commentCount', '0')} comments — published "
            f"{snippet.get('publishedAt', 'an unknown date')}."
        )
    return (
        "YouTube video stats (views/likes/comments only — not full watch-time "
        "analytics, which isn't available here):\n" + "\n".join(lines)
    )


async def analyze_social_profile(
    session: AsyncSession,
    *,
    user: CurrentUser,
    company_id: str | None = None,
    platform: str,
    username: str,
) -> str:
    """Public-profile lookup by username — see profile_lookup.py's module
    docstring for exactly which platforms genuinely support this and
    why. Also pulls a handful of the account's actual recent posts: a
    bio says what an account *claims* to be about, but real recent posts
    are what it's actually posting, which is a much stronger niche/trend
    signal — this app's own connected account's auth is what makes that
    call, same as the profile lookup itself. Deliberately returns raw
    text rather than running a separate Claude call to pre-extract a
    "niche" — the conversational model already reading this tool result
    can reason about the niche/themes/style directly from the real bio
    and posts, the same way it already does for a company's own
    onboarded profile."""
    # Every failure path below ends the same way on purpose: the user
    # still has a real account in mind, they just can't get it looked up
    # automatically. Asking them to describe it — niche, content style,
    # what they post about — and using THAT as real context is a genuine
    # fallback, not a consolation prize; create_content_item already
    # accepts free-form context in its `topic`, so a manual description
    # slots in exactly the same way a fetched profile would.
    _manual_fallback = (
        " Tell me what this account posts about — its niche, topics, style — "
        "and I'll use that the same way I'd use a fetched profile."
    )

    if platform not in profile_lookup.SUPPORTED_PLATFORMS:
        return (
            f"Looking up an arbitrary public {platform} profile isn't possible — "
            f"{platform}'s own API only allows querying an account you (or a connected "
            "company) actually manage, not any public account by username. This is a "
            "real platform limitation confirmed against its API, not something a code "
            "change can work around. Twitter/X, YouTube, and Facebook (best-effort) do "
            "support looking up any public account." + _manual_fallback
        )

    parsed, error = await _resolve_company_id(session, user, company_id)
    if error:
        return error

    connection = (
        await session.execute(
            select(PlatformConnection).where(
                PlatformConnection.company_id == parsed,
                PlatformConnection.platform == platform,
            )
        )
    ).scalar_one_or_none()
    if connection is None or connection.composio_connected_account_id is None:
        return (
            f"This company doesn't have a connected {platform} account yet. Looking up "
            f"any {platform} profile — even someone else's — has to run through a real "
            f"authenticated connection; connect one from the Integrations page first."
            + _manual_fallback
        )

    profile = await profile_lookup.fetch_public_profile(platform, connection, username)
    if profile is None:
        return (
            f"Couldn't find a {platform} profile for '{username}' — double-check the "
            "spelling, or the account may not be public." + _manual_fallback
        )

    lines = [
        f"{profile['platform'].title()} profile: {profile['name'] or profile['handle']} "
        f"(@{profile['handle']})" if profile["handle"] else f"{profile['platform'].title()} profile: {profile['name']}"
    ]
    if profile["followers"] is not None:
        lines.append(f"Followers: {profile['followers']}")
    if profile["location"]:
        lines.append(f"Location: {profile['location']}")
    if profile["bio"]:
        lines.append(f"Bio: {profile['bio']}")
    if profile["url"]:
        lines.append(f"URL: {profile['url']}")

    # The account's own handle (not the raw `username` argument, which
    # might be a pasted URL or missing a leading '@') is what each
    # fetcher actually expects.
    posts = await profile_lookup.fetch_recent_posts(
        platform, connection, profile["handle"] or username
    )
    if posts:
        lines.append("")
        lines.append(
            "Recent posts — read these for the account's ACTUAL niche/topics/style, "
            "not just what the bio claims:"
        )
        for post in posts:
            text = post.get("text") or post.get("title") or "(no text)"
            lines.append(f"- {text}")
    elif platform == "twitter":
        # Not a real "no content" claim — Recent Search only covers the
        # last 7 days, a genuine API limitation, not this account having
        # nothing to show.
        lines.append("")
        lines.append(
            "(No posts in the last 7 days — X's search API only covers that window, "
            "so this doesn't mean the account is inactive.)"
        )

    return "\n".join(lines)


TOOL_IMPLEMENTATIONS = {
    "list_companies": list_companies,
    "list_trending_topics": list_trending_topics,
    "get_company_summary": get_company_summary,
    "search_knowledge_base": search_knowledge_base,
    "save_to_knowledge_base": save_to_knowledge_base,
    "get_content_pipeline_status": get_content_pipeline_status,
    "find_content_items": find_content_items,
    "create_content_item": create_content_item,
    "get_youtube_video_analytics": get_youtube_video_analytics,
    "analyze_social_profile": analyze_social_profile,
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
            "create or generate a new content plan/calendar. company_id is "
            "OPTIONAL — omit it to use the one company on the account (or ask "
            "which one, if there's more than one). Never ask the user for a "
            "UUID directly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": "string",
                    "description": "The company's UUID — OPTIONAL, resolved automatically if omitted.",
                },
                "days": {
                    "type": "integer",
                    "description": "Number of days the plan should cover (optional).",
                },
            },
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
        "name": "delete_content_item_post",
        "description": (
            "Permanently deletes an already-published post from its real "
            "platform (LinkedIn, Facebook, or YouTube — Instagram has no "
            "delete capability at all, say so plainly if asked). Genuinely "
            "irreversible and public-facing — only call this when the user "
            "has clearly and explicitly asked to delete/remove/take down/"
            "unpublish a SPECIFIC already-published item. Never call this "
            "speculatively or as a suggestion. Requires content_item_id — "
            "use find_content_items first if you don't already have it."
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
    {
        "name": "upload_youtube_video",
        "description": (
            "Upload an actual video file — attached earlier in this conversation — as "
            "a real YouTube video. This is completely different from a YouTube text/"
            "community post, which is impossible (YouTube's API has no such action, "
            "and never will via a config change — don't suggest one). Only call this "
            "when the user has explicitly asked to upload a specific attached video to "
            "YouTube. video_url must be the exact attachment URL already present in "
            "this conversation — never invent, guess, or reuse a URL from a different "
            "attachment. privacy_status defaults to 'unlisted' (reachable only by "
            "direct link, not publicly searchable) so nothing goes fully public by "
            "accident — only set it to 'public' or 'private' when the user has "
            "explicitly asked for that. A real, irreversible action: always propose "
            "it, never assume consent."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "video_url": {
                    "type": "string",
                    "description": "The exact attachment URL from this conversation.",
                },
                "title": {"type": "string", "description": "The video's title."},
                "description": {"type": "string", "description": "The video's description."},
                "company_id": {
                    "type": "string",
                    "description": "The company's UUID — OPTIONAL, resolved automatically if omitted.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional keyword tags for discoverability.",
                },
                "privacy_status": {
                    "type": "string",
                    "enum": ["unlisted", "public", "private"],
                    "description": (
                        "Defaults to 'unlisted' if omitted. Only set to 'public' or "
                        "'private' when the user has explicitly said so."
                    ),
                },
            },
            "required": ["video_url", "title", "description"],
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
    session: AsyncSession, *, user: CurrentUser, company_id: str | None = None, days: int | None = None
) -> str:
    parsed, error = await _resolve_company_id(session, user, company_id)
    if error:
        return error
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
        execution_id = await publish_post(session, connection, item.draft_copy, media_url=item.media_url)
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
    # Best-effort — get_post_url never raises, so a lookup failure just
    # means no link in the confirmation, not a broken/misleading success
    # message about a publish that genuinely succeeded.
    post_url = await get_post_url(connection, execution_id)
    link_suffix = f" {post_url}" if post_url else ""
    return f"Published '{item.title}' to {item.platform}.{link_suffix}"


async def delete_content_item_post(session: AsyncSession, *, content_item_id: str) -> str:
    """Permanently deletes a previously-published post from its real
    platform — genuinely irreversible, which is why this tool is gated
    behind a typed confirmation in the UI on top of the normal Confirm/
    Cancel (see agent.py's `_TYPED_CONFIRMATION_PHRASE_BY_TOOL`), not just
    a single click like every other write tool here."""
    parsed = _parse_uuid(content_item_id, "content_item_id")
    if parsed is None:
        return f"'{content_item_id}' isn't a valid content item id."
    item = await session.get(ContentItem, parsed)
    if item is None:
        return f"No content item found with id {content_item_id}."
    if item.published_at is None:
        return f"'{item.title}' hasn't been published, so there's nothing to delete."

    connection = (
        await session.execute(
            select(PublishAttempt, PlatformConnection)
            .join(PlatformConnection, PublishAttempt.platform_connection_id == PlatformConnection.id)
            .where(PublishAttempt.content_item_id == item.id, PublishAttempt.status == "success")
            .order_by(PublishAttempt.attempted_at.desc())
            .limit(1)
        )
    ).first()
    if connection is None:
        return (
            f"Couldn't find a record of where '{item.title}' was actually posted — "
            "can't delete it through this app."
        )
    attempt, platform_connection = connection
    if not attempt.composio_execution_id:
        return (
            f"'{item.title}' has no real post id on file — can't delete it through "
            "this app."
        )

    try:
        if item.platform == "youtube":
            await delete_youtube_video(platform_connection, attempt.composio_execution_id)
        else:
            await delete_post(platform_connection, attempt.composio_execution_id)
    except DeleteNotSupportedError as exc:
        return str(exc)
    except Exception as exc:
        return f"Deleting '{item.title}' failed: {str(exc)[:300]}"

    item.published_at = None
    await session.commit()
    return f"Deleted '{item.title}' from {item.platform}. It's no longer live."


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


_YOUTUBE_PRIVACY_STATUSES = {"unlisted", "public", "private"}


async def upload_youtube_video_tool(
    session: AsyncSession,
    *,
    user: CurrentUser,
    video_url: str,
    title: str,
    description: str,
    company_id: str | None = None,
    tags: list[str] | None = None,
    privacy_status: str = "unlisted",
) -> str:
    if privacy_status not in _YOUTUBE_PRIVACY_STATUSES:
        return (
            f"'{privacy_status}' isn't a valid YouTube privacy setting — "
            "use unlisted, public, or private."
        )

    parsed, error = await _resolve_company_id(session, user, company_id)
    if error:
        return error

    connection = (
        await session.execute(
            select(PlatformConnection).where(
                PlatformConnection.company_id == parsed,
                PlatformConnection.platform == "youtube",
            )
        )
    ).scalar_one_or_none()
    if connection is None or connection.status != "connected" or connection.composio_connected_account_id is None:
        return "YouTube isn't connected for this company yet — connect it from Integrations first."

    # Queued rather than a single synchronous attempt — a real upload is
    # three sequential network hops (fetch the video, a presigned S3
    # upload, Composio's own YouTube call), any of which can fail
    # transiently without the upload itself being wrong. This makes one
    # immediate attempt and, if that doesn't succeed outright,
    # `run_scheduled_youtube_uploads` keeps retrying it in the background
    # rather than the user having to notice a failure and re-ask.
    job = await enqueue_youtube_upload(
        session, connection, video_url, title, description, tags=tags, privacy_status=privacy_status
    )
    if job.status == "success":
        video_url = get_video_url(job.composio_execution_id) if job.composio_execution_id else None
        return (
            f'Uploaded "{title}" to YouTube as {privacy_status} — {video_url}'
            if video_url
            else f'Uploaded "{title}" to YouTube as {privacy_status} — execution id {job.composio_execution_id}.'
        )
    if job.status == "failed":
        return f"YouTube upload failed permanently: {job.status_error}"
    return (
        f'"{title}" is queued for YouTube — the first attempt hit a snag '
        f"({job.status_error}), retrying automatically every "
        f"{settings.YOUTUBE_UPLOAD_SCHEDULER_INTERVAL_MINUTES} minutes for up to "
        f"{settings.MAX_YOUTUBE_UPLOAD_ATTEMPTS} attempts. No need to re-ask."
    )


WRITE_TOOL_IMPLEMENTATIONS = {
    "approve_content_item": approve_content_item,
    "reject_content_item": reject_content_item,
    "regenerate_content_item_draft": regenerate_content_item_draft,
    "create_content_plan": create_content_plan,
    "publish_content_item": publish_content_item,
    "delete_content_item_post": delete_content_item_post,
    "schedule_content_item": schedule_content_item,
    "upload_youtube_video": upload_youtube_video_tool,
}
