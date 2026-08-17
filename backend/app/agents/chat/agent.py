"""The chat agent's multi-turn tool-use loop.

Every other agent in this codebase makes a single forced-tool Claude call
(`tool_choice={"type": "tool", "name": "..."}`) and parses one response —
see `content_management/strategy.py` for the canonical example. A chat
agent can't work that way: it needs to decide per-turn whether calling a
tool makes sense at all (a forced tool call on "hello" would hallucinate
one), so this is `tool_choice: auto` with real `stop_reason` branching and
a bounded loop — the one genuinely new architectural pattern here.
"""

from __future__ import annotations

import inspect
import logging
import uuid
from collections.abc import AsyncGenerator

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat.tools import (
    TOOL_IMPLEMENTATIONS,
    TOOL_SCHEMAS,
    WRITE_TOOL_IMPLEMENTATIONS,
    WRITE_TOOL_SCHEMAS,
    _content_item_card,
)
from app.config import settings
from app.db.models import Company, ContentItem, ContentPlan
from app.security.auth import CurrentUser

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"  # matches every other agent's hardcoded model

_ALL_SCHEMAS = TOOL_SCHEMAS + WRITE_TOOL_SCHEMAS

# Write tools that act on one existing item, identified by content_item_id
# — for these, the *proposal* (before confirm) can already show a preview
# card of the exact item about to be acted on, not just its id in a
# sentence.
_ITEM_WRITE_TOOLS = {
    "approve_content_item",
    "reject_content_item",
    "regenerate_content_item_draft",
    "publish_content_item",
    "delete_content_item_post",
    "schedule_content_item",
}

# Write tools whose real-world consequence is severe/irreversible enough
# to need more than the normal single-click Confirm — the UI shows a text
# field requiring this exact phrase before Confirm is even enabled.
# Deleting a live, public post is the first of these: unlike every other
# write tool here (publish, schedule, approve/reject/regenerate — all
# either reversible or a first-time action), there's no undo once a real
# post is gone from LinkedIn/Facebook/YouTube.
_TYPED_CONFIRMATION_PHRASE_BY_TOOL = {
    "delete_content_item_post": "DELETE",
}

_SYSTEM_PROMPT = """\
You are LoomVerse AI — the intelligent core of LoomVerse, an AI-native \
Content Operating System. You are not a generic AI chatbot, a writing \
assistant, or a social media scheduler. You are an embedded AI content \
team: equal parts experienced content strategist, social media manager, \
campaign planner, and operations manager — working entirely inside this \
platform on behalf of the user's business.

## What LoomVerse Is

LoomVerse is a complete Content Operating System. It manages the full \
content lifecycle — from understanding a business's identity and goals, \
through trend intelligence and strategic planning, to creation, approval \
workflows, publishing, and performance analysis. It is built around the \
idea that great content is the output of a complete, repeatable workflow, \
not a single AI-generated post.

LoomVerse helps businesses, agencies, startups, creators, and marketing \
teams eliminate repetitive work, maintain strategic direction, and produce \
high-quality content consistently — across every platform, every week.

## What You Know About the User's Business

Before generating any content or recommendation, you work from the \
business's own onboarded profile — its industry, audience, brand voice, \
unique value proposition, existing campaigns, knowledge base (scraped \
site content, uploaded documents, approved posts), trend intelligence \
calibrated to that business, and publishing history. You never generate \
generic content when company context is available. Always retrieve it \
first.

## Your Capabilities (via tools available in this conversation)

**Company Intelligence**
- Retrieve a company's onboarded profile: industry, audience, brand \
voice, summary, and strategic context (`get_company_summary`).
- Search the company's knowledge base: website content, uploaded \
documents, historical approved content (`search_knowledge_base`).

**Content Pipeline & Status**
- Check the current pipeline: strategies, content plans, campaigns, and \
their approval states (`get_content_pipeline_status`).
- Find specific content items by title or platform (`find_content_items`).

**Trend Intelligence**
- Surface trending topics ranked by relevance to this company's brand and \
industry (`list_trending_topics`). Explain why each trend matters and how \
to act on it. Every result includes a real id and a one-line insight — \
always quote the id verbatim if the user then wants content built around \
one of them. This always returns the best available trends, even when \
none are a strong match — check the relevance score on each: above ~0.5 \
is a real match worth treating as trending, below that is weak, and you \
should say so plainly ("nothing's a strong trend match right now, but the \
closest is...") rather than presenting a weak match as if it were solid. \
Never claim there's nothing to work with when this tool returned results \
at all — call it before writing anything the user frames as trend-driven, \
so it's a real trend informing the content, not an invented one.

**Content Creation**
- Write a single ready-to-publish post immediately — LinkedIn, Instagram, \
X, TikTok, Facebook, Threads, YouTube, blog, newsletter, carousel, \
podcast, or any other supported format — tailored to the platform's tone, \
structure, and audience (`create_content_item`). If media is attached in \
the message as a markdown link, incorporate it. Every post already draws \
on this company's own currently-relevant trends automatically — you never \
need to ask "what's trending" first just to write a normal post. When the \
user wants a post built around one SPECIFIC trend (from something \
`list_trending_topics` surfaced, or that they name directly), pass that \
trend's real id as `trend_id` so it's genuinely the center of the post, \
not just background context, and stays linked back to it.
- Build a full content calendar spanning multiple days with platform mix, \
campaign alignment, and scheduling (`create_content_plan` — requires \
user confirmation before executing).

**Approval & Workflow**
- Approve, reject, or regenerate an existing draft (`approve_content_item` \
/ `reject_content_item` / `regenerate_content_item_draft` — each requires \
confirmation).

**Publishing & Scheduling**
- Publish a post immediately to its connected platform \
(`publish_content_item` — requires confirmation).
- Schedule a post for a future time (`schedule_content_item` — requires \
confirmation).
- Permanently delete an already-published post from its real platform \
(`delete_content_item_post` — requires confirmation, plus the user must \
type an exact phrase to actually confirm it, not just click a button, \
since this is genuinely irreversible and public-facing). Only supported \
for LinkedIn, Facebook, and YouTube — Instagram has no delete capability \
at all; if asked to delete an Instagram post, say so plainly and point \
them to Instagram itself, never attempt it. Only call this when the user \
has clearly and explicitly asked to delete/remove/take down/unpublish a \
specific already-published item — never speculatively.
- Upload an actual attached video file as a real YouTube video \
(`upload_youtube_video` — requires confirmation). Defaults to 'unlisted' \
(reachable only by direct link) so nothing goes public by accident — set \
`privacy_status` to 'public' or 'private' only when the user has \
explicitly asked for that. This is NOT the same thing as a YouTube text/\
community post — that has no API at all and is never possible, no matter \
what the user asks for or how the request is phrased; if someone asks \
for a YouTube "post" and hasn't attached an actual video file, say \
plainly that YouTube has no text-post capability and ask if they'd like \
a different platform's post instead, or a real video upload if they \
have footage to attach.

**YouTube video analytics**
- Real view/like/comment counts for a video this app has uploaded, \
straight from YouTube's own API (`get_youtube_video_analytics`). This is \
NOT full YouTube Studio-grade analytics — no watch time, audience \
retention, or traffic-source breakdowns are available through this app. \
If the user wants that deeper level, say plainly that only view/like/\
comment counts are available here and point them to YouTube Studio \
directly — never fabricate numbers you don't have.

**What lives in the Content Studio workspace, not this chat yet:**
Creative briefs, post repurposing to another platform/format, and \
performance analytics beyond YouTube's own view/like/comment counts \
(engagement, reach, growth charts for other platforms). If a user asks \
for one of these, say so plainly and direct them to Content Studio — \
never attempt it or fabricate numbers.

## How You Should Behave

**Think and act like a content strategist, not a chatbot.**
Every response should reflect deep understanding of the user's business \
context, their current content pipeline, and the current trend landscape. \
Prioritize actionable, specific recommendations over generic advice.

**Use all available context first.**
Before answering any content question, retrieve the relevant company \
profile and knowledge base data. Do not ask the user to repeat information \
that is already onboarded.

**Be proactive, not just reactive.**
Identify opportunities, surface bottlenecks, flag content that needs \
attention, and recommend next steps in the workflow (draft → review → \
approve → schedule → publish → analyze) — but only when it genuinely \
helps, not as filler.

**Explain your reasoning on important decisions.**
If you recommend a specific platform, format, posting time, or campaign \
direction, briefly explain why — based on the company's audience, brand \
voice, and current trends.

**Match response depth to the question.**
Simple requests (write me a LinkedIn post) get a focused, direct \
response. Strategic questions (plan next month's content for this client) \
get comprehensive, structured guidance.

**Write-tool mechanics:**
Creating a draft (`create_content_item`) has no real-world consequence — \
run it immediately once you have enough information. All other write tools \
(publish, schedule, approve, reject, regenerate, create_content_plan) \
carry real consequences and must always be proposed first, then confirmed \
by the user before executing. Never speculatively propose a write action; \
only propose it when the user has clearly asked for that specific action.

Once a draft is created, do not by default ask what to do with it next — \
show the user the card and let them decide. They can say "post it now" or \
"schedule it for Friday 9am" when ready.

Every content item's real id is printed in `create_content_item`'s and \
`find_content_items`' own result text as "(id: ...)" — always quote that \
id verbatim for a follow-up approve/reject/regenerate/publish/schedule \
call on the same item. Never invent, guess, or reuse an id from a \
different item; if you don't see one in a tool result, call \
find_content_items again rather than guessing.

**Only call a tool when it's genuinely useful.**
For greetings, general product questions, or context already in the \
conversation, answer directly without a tool call.

**Never discuss internal configuration.**
Never mention, name, or ask the user for an API key, environment \
variable, config file (e.g. ".env"), or any other internal setup detail — \
not even to explain why something failed, and not even if one appears \
somewhere earlier in this conversation's own history (an old message \
might predate this rule). If a platform "isn't set up yet," say exactly \
that and nothing more technical; never ask the user to supply, paste, or \
confirm a credential of any kind in chat under any circumstance.

## Product Philosophy

LoomVerse exists to eliminate repetitive content work, provide strategic \
intelligence, and let teams focus on creativity while the AI manages \
planning, organisation, execution, and optimisation. Every recommendation \
must be context-aware. Every action should contribute to the user's \
content goals. Every interaction should make the content workflow faster, \
smarter, and more effective.

You are not a tool the user prompts. You are their AI content team.\
"""

# Prompt caching — the system prompt and all 16 tool schemas are byte-
# identical on every single chat call (every iteration of every turn of
# every conversation, for every company), so this is the single highest-
# leverage place in the app for it: a 5-minute cache breakpoint here is
# shared across *concurrent conversations from different companies*, not
# just within one. `cache_control` on a content block means "cache
# everything up to and including this block" — putting it on the system
# prompt and again on the last tool schema creates two breakpoints
# covering the whole fixed prefix (~7K tokens). A cache hit bills that
# prefix at 10% of standard input price; only the actual conversation
# history + new message still costs full price.
#
# Conversation history itself (the `messages` list, which grows across a
# turn's tool-loop iterations) is NOT cached here — it differs per
# conversation and would need converting from plain-string content to
# block form with its own breakpoint, a larger change than this one. The
# fixed prefix below is the 90% win for a fraction of the risk.
_SYSTEM_PROMPT_BLOCKS = [
    {"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
]
_CACHED_SCHEMAS = [
    *_ALL_SCHEMAS[:-1],
    {**_ALL_SCHEMAS[-1], "cache_control": {"type": "ephemeral"}},
]

_NOT_CONFIGURED_MESSAGE = "Chat isn't available right now — the AI service isn't configured."
_FAILURE_MESSAGE = "Something went wrong answering that — try again."

_TITLE_SYSTEM_PROMPT = (
    "You name chat conversations. Given the user's opening message, reply "
    "with a short title (3-6 words) that captures what they actually want "
    "— the intent, not a restatement of their wording. Title Case, no "
    "trailing punctuation, no quotes. Reply with the title and nothing "
    "else."
)


async def _describe_action(tool_name: str, tool_input: dict, session: AsyncSession) -> str:
    """Human-facing description of a proposed write action — a title or
    company name, never a raw UUID. `tool_input`'s ids came from Claude,
    unvalidated until confirm time, so a bad/unknown id here just falls
    back to a generic phrase rather than erroring — the proposal itself
    still stands regardless of what this text says."""

    async def _item_title() -> str:
        content_item_id = tool_input.get("content_item_id")
        if not content_item_id:
            return "that item"
        try:
            parsed = uuid.UUID(str(content_item_id))
        except (ValueError, AttributeError, TypeError):
            return "that item"
        item = await session.get(ContentItem, parsed)
        return f'"{item.title}"' if item else "that item"

    async def _company_name() -> str:
        company_id = tool_input.get("company_id")
        if not company_id:
            return "your company"
        try:
            parsed = uuid.UUID(str(company_id))
        except (ValueError, AttributeError, TypeError):
            return "your company"
        company = await session.get(Company, parsed)
        return (company.name or company.url) if company else "your company"

    if tool_name == "approve_content_item":
        return f"Approve {await _item_title()}"
    if tool_name == "reject_content_item":
        return f"Reject {await _item_title()}"
    if tool_name == "regenerate_content_item_draft":
        return f"Regenerate draft for {await _item_title()}"
    if tool_name == "create_content_plan":
        days = tool_input.get("days")
        suffix = f" ({days} days)" if days else ""
        return f"Create a new content plan for {await _company_name()}{suffix}"
    if tool_name == "publish_content_item":
        return f"Publish {await _item_title()} now"
    if tool_name == "delete_content_item_post":
        return f"Permanently delete {await _item_title()} from its platform"
    if tool_name == "schedule_content_item":
        return f"Schedule {await _item_title()} for {tool_input.get('scheduled_at')}"
    if tool_name == "upload_youtube_video":
        title = tool_input.get("title")
        privacy = tool_input.get("privacy_status") or "unlisted"
        video = f'"{title}"' if title else "that video"
        return f"Upload {video} to YouTube ({privacy})"
    return f"Run {tool_name}"


def _merge_cards(existing: list[dict], new: list[dict]) -> list[dict]:
    """Appends `new` onto `existing`, skipping any card whose (type, id)
    already appears — the same item can legitimately surface from more
    than one tool call in a single turn (e.g. Claude calling
    `find_content_items` twice, or finding an item and then proposing a
    write action on it), and without this every one of those cards ends
    up rendered as a sibling with a duplicate React key on the frontend,
    not just redundant data."""
    seen = {(card.get("type"), card.get("id")) for card in existing}
    merged = list(existing)
    for card in new:
        key = (card.get("type"), card.get("id"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(card)
    return merged


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


def _extract_text(content_blocks) -> str:
    return "".join(block.text for block in content_blocks if block.type == "text")


async def _execute_tool(
    name: str,
    tool_input: dict,
    company_id: uuid.UUID | None,
    session: AsyncSession,
    user: CurrentUser,
) -> tuple[str, list[dict]]:
    """Runs one read tool and always returns `(tool_result_text, cards)` —
    most implementations only return plain text (no cards to show), which
    this normalizes to `(text, [])` so every caller here has one uniform
    shape to deal with regardless of which specific tool ran."""
    impl = TOOL_IMPLEMENTATIONS.get(name)
    if impl is None:
        return f"Unknown tool: {name}", []

    kwargs = dict(tool_input)
    params = inspect.signature(impl).parameters
    # A conversation scoped to a company defaults its tool calls to that
    # company when Claude doesn't supply one explicitly — lets "what's
    # trending" style questions inside a company-scoped chat implicitly
    # mean "for this company" without the user having to repeat the id.
    if company_id is not None and "company_id" in params:
        kwargs.setdefault("company_id", str(company_id))
    # Tools that need to resolve "which companies can this person even see"
    # (list_companies; create_content_item's no-company-named fallback)
    # declare a `user` parameter — same opt-in-by-signature convention as
    # company_id above, so tools that don't need it stay untouched.
    if "user" in params:
        kwargs.setdefault("user", user)

    try:
        result = await impl(session, **kwargs)
    except Exception:
        logger.exception("Chat tool %s failed", name)
        return f"Tool {name} failed to run.", []
    return result if isinstance(result, tuple) else (result, [])


async def generate_conversation_title(user_message: str) -> str | None:
    """Best-effort short title capturing the *intent* of a conversation's
    opening message (e.g. "hi what can you do" -> "Exploring Assistant
    Capabilities"), replacing the old behavior of just truncating the raw
    message. Returns None on a missing key or any failure so the caller
    can fall back to truncation — same graceful-degradation contract as
    `run_chat_turn`, just quieter since this is never the user-visible
    reply."""
    if not settings.ANTHROPIC_API_KEY:
        return None
    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=20,
            system=_TITLE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        title = _extract_text(response.content).strip().strip("\"'")
        return title or None
    except Exception:
        logger.exception("Conversation title generation failed")
        return None


async def _preview_card_for_write_tool(
    tool_name: str, tool_input: dict, session: AsyncSession
) -> list[dict]:
    """A write-tool *proposal* (before confirm) can already show the real
    item it's about to act on, for the tools that target one existing item
    by id — approve/reject/regenerate/publish/schedule. Best-effort: an
    invalid id or a lookup failure just means no preview card, never an
    error (the proposal itself still stands; confirming it will surface
    the same "not found" message the tool always would). Just a lookup, no
    access check — the real one runs at confirm time
    (`_ensure_action_target_allowed` in chat.py), same as the write tools
    themselves don't check access either."""
    if tool_name not in _ITEM_WRITE_TOOLS:
        return []
    content_item_id = tool_input.get("content_item_id")
    if not content_item_id:
        return []
    try:
        parsed = uuid.UUID(content_item_id)
    except (ValueError, AttributeError, TypeError):
        return []
    item = await session.get(ContentItem, parsed)
    if item is None:
        return []
    content_plan = await session.get(ContentPlan, item.content_plan_id)
    if content_plan is None:
        return []
    return [_content_item_card(item, content_plan.company_id)]


async def run_chat_turn(
    conversation_history: list[dict],
    company_id: uuid.UUID | None,
    session: AsyncSession,
    user: CurrentUser,
) -> tuple[str, list[str], bool, dict | None, list[dict]]:
    """Run one assistant turn given the full prior conversation history
    (already including the new user message). Returns
    (assistant_text, tool_names_used, ok, proposed_action, cards).
    `proposed_action` is non-null exactly when the model wants to run a
    write tool — that tool is never executed here, the turn just ends with
    the proposal. `cards` are small structured snapshots (a content item,
    a trend) accumulated from every tool call this turn made, for the
    frontend to render as flashcards — most turns produce none. Never
    raises — same graceful-degradation contract as every other agent: on a
    missing key or any failure, returns a clear message, not a 500."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping chat turn")
        return (_NOT_CONFIGURED_MESSAGE, [], False, None, [])

    messages = list(conversation_history)
    tools_used: list[str] = []
    cards: list[dict] = []
    try:
        for _ in range(settings.CHAT_MAX_ITERATIONS):
            response = await _client().messages.create(
                model=_MODEL,
                max_tokens=settings.CHAT_MAX_TOKENS,
                system=_SYSTEM_PROMPT_BLOCKS,
                tools=_CACHED_SCHEMAS,
                tool_choice={"type": "auto"},
                messages=messages,
            )
            if response.stop_reason != "tool_use":
                return (_extract_text(response.content), tools_used, True, None, cards)

            write_block = next(
                (
                    b
                    for b in response.content
                    if b.type == "tool_use" and b.name in WRITE_TOOL_IMPLEMENTATIONS
                ),
                None,
            )
            if write_block is not None:
                write_input = dict(write_block.input)
                write_impl = WRITE_TOOL_IMPLEMENTATIONS.get(write_block.name)
                if (
                    company_id is not None
                    and write_impl is not None
                    and "company_id" in inspect.signature(write_impl).parameters
                ):
                    write_input.setdefault("company_id", str(company_id))
                proposed_action = {
                    "tool_name": write_block.name,
                    "tool_input": write_input,
                    "description": await _describe_action(write_block.name, write_input, session),
                    # None for every write tool except the ones severe/
                    # irreversible enough to need more than a single
                    # click — the frontend only shows the typed-
                    # confirmation field when this is set.
                    "confirmation_phrase": _TYPED_CONFIRMATION_PHRASE_BY_TOOL.get(write_block.name),
                }
                text = _extract_text(response.content) or proposed_action["description"]
                preview_cards = await _preview_card_for_write_tool(
                    write_block.name, write_input, session
                )
                return (text, tools_used, True, proposed_action, _merge_cards(cards, preview_cards))

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                tools_used.append(block.name)
                result, result_cards = await _execute_tool(
                    block.name, block.input, company_id, session, user
                )
                cards = _merge_cards(cards, result_cards)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                )
            messages.append({"role": "user", "content": tool_results})

        # Iteration cap hit — force a final answer with tools disabled.
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=settings.CHAT_MAX_TOKENS,
            system=_SYSTEM_PROMPT_BLOCKS,
            tools=_CACHED_SCHEMAS,
            tool_choice={"type": "none"},
            messages=messages,
        )
        return (_extract_text(response.content), tools_used, True, None, cards)
    except Exception:
        logger.exception("Chat turn failed")
        return (_FAILURE_MESSAGE, tools_used, False, None, [])


# ── Streaming variant ────────────────────────────────────────────────────────
# Tool calls cannot stream mid-loop — they run as normal blocking calls
# exactly as run_chat_turn does. Only the *final* text-generation step
# (no more tool calls) uses messages.stream() so tokens appear immediately.
# The generator yields plain text chunks; the caller (the SSE endpoint)
# wraps them in SSE framing.

class _StreamDone(Exception):
    """Internal sentinel: final answer has been fully streamed."""
    def __init__(
        self,
        tools_used: list[str],
        proposed_action: dict | None,
        cards: list[dict],
    ) -> None:
        self.tools_used = tools_used
        self.proposed_action = proposed_action
        self.cards = cards


async def run_chat_turn_stream(
    conversation_history: list[dict],
    company_id: uuid.UUID | None,
    session: AsyncSession,
    user: CurrentUser,
) -> AsyncGenerator[tuple[str, str, list[str], dict | None, list[dict]], None]:
    """Streaming version of run_chat_turn.

    Yields ``(event_type, payload)`` tuples where ``event_type`` is one of:
    - ``"token"``  — ``payload`` is a raw text chunk from the model
    - ``"tool"``   — ``payload`` is a tool name (shown as a "thinking" hint)
    - ``"done"``   — ``payload`` is a JSON-serialisable dict with the final
                     metadata: tools_used, proposed_action, cards, ok

    Never raises — errors are yielded as ``("error", message)``.
    """
    if not settings.ANTHROPIC_API_KEY:
        yield ("error", _NOT_CONFIGURED_MESSAGE)
        return

    messages = list(conversation_history)
    tools_used: list[str] = []
    cards: list[dict] = []

    try:
        for _ in range(settings.CHAT_MAX_ITERATIONS):
            # ── Non-streaming pass: let Claude decide whether to use tools ──
            response = await _client().messages.create(
                model=_MODEL,
                max_tokens=settings.CHAT_MAX_TOKENS,
                system=_SYSTEM_PROMPT_BLOCKS,
                tools=_CACHED_SCHEMAS,
                tool_choice={"type": "auto"},
                messages=messages,
            )

            # ── No tool call → stream the final answer ──────────────────────
            if response.stop_reason != "tool_use":
                # Re-request the same turn with streaming enabled.
                # We already paid one non-streaming call to resolve tool use;
                # this second call gives us the final text as a stream.
                async with _client().messages.stream(
                    model=_MODEL,
                    max_tokens=settings.CHAT_MAX_TOKENS,
                    system=_SYSTEM_PROMPT_BLOCKS,
                    tools=_CACHED_SCHEMAS,
                    tool_choice={"type": "none"},
                    messages=messages,
                ) as stream:
                    async for text_chunk in stream.text_stream:
                        yield ("token", text_chunk)
                yield (
                    "done",
                    {
                        "tools_used": tools_used,
                        "proposed_action": None,
                        "cards": cards,
                        "ok": True,
                    },
                )
                return

            # ── Write tool → propose it without executing ───────────────────
            write_block = next(
                (
                    b
                    for b in response.content
                    if b.type == "tool_use" and b.name in WRITE_TOOL_IMPLEMENTATIONS
                ),
                None,
            )
            if write_block is not None:
                write_input = dict(write_block.input)
                write_impl = WRITE_TOOL_IMPLEMENTATIONS.get(write_block.name)
                if (
                    company_id is not None
                    and write_impl is not None
                    and "company_id" in inspect.signature(write_impl).parameters
                ):
                    write_input.setdefault("company_id", str(company_id))
                proposed_action = {
                    "tool_name": write_block.name,
                    "tool_input": write_input,
                    "description": await _describe_action(write_block.name, write_input, session),
                    # None for every write tool except the ones severe/
                    # irreversible enough to need more than a single
                    # click — the frontend only shows the typed-
                    # confirmation field when this is set.
                    "confirmation_phrase": _TYPED_CONFIRMATION_PHRASE_BY_TOOL.get(write_block.name),
                }
                text = _extract_text(response.content) or proposed_action["description"]
                preview_cards = await _preview_card_for_write_tool(
                    write_block.name, write_input, session
                )
                # Emit the proposal text as tokens so it streams in too
                for word in text.split(" "):
                    yield ("token", word + " ")
                yield (
                    "done",
                    {
                        "tools_used": tools_used,
                        "proposed_action": proposed_action,
                        "cards": _merge_cards(cards, preview_cards),
                        "ok": True,
                    },
                )
                return

            # ── Read tool → execute, then loop ─────────────────────────────
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                tools_used.append(block.name)
                yield ("tool", block.name)
                result, result_cards = await _execute_tool(
                    block.name, block.input, company_id, session, user
                )
                cards = _merge_cards(cards, result_cards)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                )
            messages.append({"role": "user", "content": tool_results})

        # ── Iteration cap — stream a forced final answer ────────────────────
        async with _client().messages.stream(
            model=_MODEL,
            max_tokens=settings.CHAT_MAX_TOKENS,
            system=_SYSTEM_PROMPT_BLOCKS,
            tools=_CACHED_SCHEMAS,
            tool_choice={"type": "none"},
            messages=messages,
        ) as stream:
            async for text_chunk in stream.text_stream:
                yield ("token", text_chunk)
        yield ("done", {"tools_used": tools_used, "proposed_action": None, "cards": cards, "ok": True})

    except Exception:
        logger.exception("Streaming chat turn failed")
        yield ("error", _FAILURE_MESSAGE)
