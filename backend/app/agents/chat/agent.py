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
from app.db.models import ContentItem, ContentPlan

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
    "schedule_content_item",
}

_SYSTEM_PROMPT = (
    "You are the LoomVerse AI assistant, embedded in a marketing intelligence "
    "tool. Answer the user's questions about their own data — companies, "
    "trends, content pipeline status, knowledge base content — using the "
    "tools available to you. Only call a tool when it's genuinely useful for "
    "answering the question; for greetings or general questions, just answer "
    "directly. Be concise and direct, never pad an answer with filler.\n\n"
    "When someone describes one post they want written — including "
    "attaching an image or file, which appears in their message as a "
    "markdown link — write it with create_content_item once you have "
    "enough to go on (what it's about, ideally which platform); if the "
    "request is vague, ask a clarifying question first instead of "
    "guessing. That's different from create_content_plan, which builds a "
    "whole calendar of several posts, not one. Creating a draft has no "
    "real-world consequence, so create_content_item runs immediately — no "
    "confirmation needed. Publishing or scheduling it for real "
    "(publish_content_item, schedule_content_item) does need confirmation, "
    "same as approve/reject/regenerate/create_content_plan: calling one of "
    "those only proposes it, and a human has to confirm before anything "
    "happens. Only propose one when the user has clearly asked for that "
    "specific action, not speculatively — and once a post exists, don't "
    "ask what to do with it next by default; the user can act on the card "
    "shown to them, or tell you directly (\"post it now\", \"schedule it "
    "for Friday 9am\")."
)

_NOT_CONFIGURED_MESSAGE = "Chat isn't available right now — the AI service isn't configured."
_FAILURE_MESSAGE = "Something went wrong answering that — try again."

_TITLE_SYSTEM_PROMPT = (
    "You name chat conversations. Given the user's opening message, reply "
    "with a short title (3-6 words) that captures what they actually want "
    "— the intent, not a restatement of their wording. Title Case, no "
    "trailing punctuation, no quotes. Reply with the title and nothing "
    "else."
)


def _describe_action(tool_name: str, tool_input: dict) -> str:
    if tool_name == "approve_content_item":
        return f"Approve content item {tool_input.get('content_item_id')}"
    if tool_name == "reject_content_item":
        return f"Reject content item {tool_input.get('content_item_id')}"
    if tool_name == "regenerate_content_item_draft":
        return f"Regenerate draft for content item {tool_input.get('content_item_id')}"
    if tool_name == "create_content_plan":
        days = tool_input.get("days")
        suffix = f" ({days} days)" if days else ""
        return f"Create a new content plan for company {tool_input.get('company_id')}{suffix}"
    if tool_name == "publish_content_item":
        return f"Publish content item {tool_input.get('content_item_id')} now"
    if tool_name == "schedule_content_item":
        return f"Schedule content item {tool_input.get('content_item_id')} for {tool_input.get('scheduled_at')}"
    return f"Run {tool_name}"


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


def _extract_text(content_blocks) -> str:
    return "".join(block.text for block in content_blocks if block.type == "text")


async def _execute_tool(
    name: str,
    tool_input: dict,
    company_id: uuid.UUID | None,
    session: AsyncSession,
) -> tuple[str, list[dict]]:
    """Runs one read tool and always returns `(tool_result_text, cards)` —
    most implementations only return plain text (no cards to show), which
    this normalizes to `(text, [])` so every caller here has one uniform
    shape to deal with regardless of which specific tool ran."""
    impl = TOOL_IMPLEMENTATIONS.get(name)
    if impl is None:
        return f"Unknown tool: {name}", []

    kwargs = dict(tool_input)
    # A conversation scoped to a company defaults its tool calls to that
    # company when Claude doesn't supply one explicitly — lets "what's
    # trending" style questions inside a company-scoped chat implicitly
    # mean "for this company" without the user having to repeat the id.
    if company_id is not None and "company_id" in inspect.signature(impl).parameters:
        kwargs.setdefault("company_id", str(company_id))

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
                system=_SYSTEM_PROMPT,
                tools=_ALL_SCHEMAS,
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
                # A write tool ends the turn immediately with a proposal —
                # it's never executed here, and any other tool call Claude
                # bundled into the same response is dropped along with it;
                # the whole turn just stops and waits for confirmation.
                write_input = dict(write_block.input)
                write_impl = WRITE_TOOL_IMPLEMENTATIONS.get(write_block.name)
                # Same "a company-scoped conversation defaults its tool
                # calls to that company" behavior _execute_tool applies to
                # read tools below, applied here too — Claude has no way to
                # know a company's UUID on its own (it isn't told one), so
                # without this a company-scoped chat could never propose
                # create_content_plan at all.
                if (
                    company_id is not None
                    and write_impl is not None
                    and "company_id" in inspect.signature(write_impl).parameters
                ):
                    write_input.setdefault("company_id", str(company_id))
                proposed_action = {
                    "tool_name": write_block.name,
                    "tool_input": write_input,
                    "description": _describe_action(write_block.name, write_input),
                }
                text = _extract_text(response.content) or proposed_action["description"]
                preview_cards = await _preview_card_for_write_tool(
                    write_block.name, write_input, session
                )
                return (text, tools_used, True, proposed_action, cards + preview_cards)

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                tools_used.append(block.name)
                result, result_cards = await _execute_tool(
                    block.name, block.input, company_id, session
                )
                cards.extend(result_cards)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                )
            messages.append({"role": "user", "content": tool_results})

        # Iteration cap hit — force a final answer with tools disabled so
        # the loop always terminates with a real reply, never a timeout.
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=settings.CHAT_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            tools=_ALL_SCHEMAS,
            tool_choice={"type": "none"},
            messages=messages,
        )
        return (_extract_text(response.content), tools_used, True, None, cards)
    except Exception:
        logger.exception("Chat turn failed")
        return (_FAILURE_MESSAGE, tools_used, False, None, [])
