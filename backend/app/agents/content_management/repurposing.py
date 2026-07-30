"""Content Repurposing Engine — takes one existing ContentItem's message
and re-drafts it for a different platform/content type, preserving the
core idea but adapting voice, length, and platform conventions. Same
one-shot forced-tool pattern as every other generator here, and reuses
`GeneratedContentItem`/`HUMANIZED_CONTENT_SYSTEM_PROMPT` — the output bar
is identical to fresh generation: finished, ready-to-publish copy, not a
verbatim copy-paste of the source.
"""

from __future__ import annotations

import logging
from datetime import date

from anthropic import AsyncAnthropic

from app.agents.content_management.prompts import HUMANIZED_CONTENT_SYSTEM_PROMPT
from app.agents.content_management.schemas import GeneratedContentItem
from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"

_TOOL = {
    "name": "repurpose_content_item",
    "description": "Adapt an existing post's core message into a new post for a different platform/format.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short internal title for the new post."},
            "description": {
                "type": "string",
                "description": "A one-line brief of what the new post shows/covers — for the calendar view, not the post itself",
            },
            "draft_copy": {
                "type": "string",
                "description": (
                    "The actual finished, ready-to-publish copy for the new post — not the "
                    "original text pasted verbatim, and not a brief or outline. Full caption "
                    "text adapted to the target platform's real voice and length conventions, "
                    "keeping the source's core idea/message intact."
                ),
            },
            "hashtags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Structured hashtags for the new post, without '#'. Empty array if the "
                    "target platform/format doesn't use them."
                ),
            },
        },
        "required": ["title", "description", "draft_copy"],
    },
}


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def repurpose_content_item(
    context: str,
    source_title: str,
    source_draft_copy: str,
    target_platform: str,
    target_content_type: str,
) -> tuple[GeneratedContentItem | None, bool]:
    """Never raises — returns `(None, False)` on any failure, same
    graceful-degradation contract as every other generator here."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping content repurposing")
        return None, False

    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=HUMANIZED_CONTENT_SYSTEM_PROMPT,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "repurpose_content_item"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Adapt this existing post's core message/idea into a new, finished, "
                        f"ready-to-publish {target_platform} {target_content_type} post — don't "
                        f"just copy it verbatim, rewrite it in that platform's real voice/length/"
                        f"conventions while keeping the same core idea. Use the "
                        f"`repurpose_content_item` tool.\n\n"
                        f"Original post title: {source_title}\n"
                        f"Original post copy:\n{source_draft_copy}\n\n"
                        f"{context}"
                    ),
                }
            ],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        data = tool_use.input
    except Exception:
        logger.exception("Claude content repurposing failed")
        return None, False

    if not data.get("draft_copy") or not data.get("title"):
        return None, False

    return (
        GeneratedContentItem(
            title=data["title"],
            description=data.get("description") or f'Repurposed from "{source_title}"',
            content_type=target_content_type,
            platform=target_platform,
            suggested_date=date.today(),
            hashtags=data.get("hashtags") or None,
            draft_copy=data["draft_copy"],
        ),
        True,
    )
