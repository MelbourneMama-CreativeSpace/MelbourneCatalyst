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
)
from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"  # matches every other agent's hardcoded model

_ALL_SCHEMAS = TOOL_SCHEMAS + WRITE_TOOL_SCHEMAS

_SYSTEM_PROMPT = (
    "You are the LoomVerse AI assistant, embedded in a marketing intelligence "
    "tool. Answer the user's questions about their own data — companies, "
    "trends, content pipeline status, knowledge base content — using the "
    "tools available to you. Only call a tool when it's genuinely useful for "
    "answering the question; for greetings or general questions, just answer "
    "directly. Be concise and direct, never pad an answer with filler.\n\n"
    "Some tools (approve/reject/regenerate a content item, create a content "
    "plan) make a real change. You never execute those yourself — calling "
    "one only proposes it, and a human has to confirm before anything "
    "happens. Only propose one when the user has clearly asked for that "
    "specific action, not speculatively."
)

_NOT_CONFIGURED_MESSAGE = "Chat isn't available right now — the AI service isn't configured."
_FAILURE_MESSAGE = "Something went wrong answering that — try again."


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
) -> str:
    impl = TOOL_IMPLEMENTATIONS.get(name)
    if impl is None:
        return f"Unknown tool: {name}"

    kwargs = dict(tool_input)
    # A conversation scoped to a company defaults its tool calls to that
    # company when Claude doesn't supply one explicitly — lets "what's
    # trending" style questions inside a company-scoped chat implicitly
    # mean "for this company" without the user having to repeat the id.
    if company_id is not None and "company_id" in inspect.signature(impl).parameters:
        kwargs.setdefault("company_id", str(company_id))

    try:
        return await impl(session, **kwargs)
    except Exception:
        logger.exception("Chat tool %s failed", name)
        return f"Tool {name} failed to run."


async def run_chat_turn(
    conversation_history: list[dict],
    company_id: uuid.UUID | None,
    session: AsyncSession,
) -> tuple[str, list[str], bool, dict | None]:
    """Run one assistant turn given the full prior conversation history
    (already including the new user message). Returns
    (assistant_text, tool_names_used, ok, proposed_action).
    `proposed_action` is non-null exactly when the model wants to run a
    write tool — that tool is never executed here, the turn just ends with
    the proposal. Never raises — same graceful-degradation contract as
    every other agent: on a missing key or any failure, returns a clear
    message, not a 500."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping chat turn")
        return (_NOT_CONFIGURED_MESSAGE, [], False, None)

    messages = list(conversation_history)
    tools_used: list[str] = []
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
                return (_extract_text(response.content), tools_used, True, None)

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
                proposed_action = {
                    "tool_name": write_block.name,
                    "tool_input": write_block.input,
                    "description": _describe_action(write_block.name, write_block.input),
                }
                text = _extract_text(response.content) or proposed_action["description"]
                return (text, tools_used, True, proposed_action)

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                tools_used.append(block.name)
                result = await _execute_tool(block.name, block.input, company_id, session)
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
        return (_extract_text(response.content), tools_used, True, None)
    except Exception:
        logger.exception("Chat turn failed")
        return (_FAILURE_MESSAGE, tools_used, False, None)
