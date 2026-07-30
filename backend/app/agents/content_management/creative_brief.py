"""Claude-powered Creative Brief Generator — hook, shot list, visual
direction, and editing notes for one content item. Genuinely new content,
not a repurposing of the draft copy. Same one-shot forced-tool pattern as
`quality_check.py`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from anthropic import AsyncAnthropic

from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"

_SYSTEM_PROMPT = (
    "You are a creative director putting together a production brief for a "
    "social content piece — the hook, shot list, visual direction, and "
    "editing notes a videographer/designer would actually use to produce "
    "it. Be concrete and specific to the platform and content type, not "
    "generic. A thumbnail concept only matters for video-style content — "
    "leave it empty for plain text/image posts."
)

_TOOL = {
    "name": "generate_creative_brief",
    "description": "Produce a creative production brief for one piece of content.",
    "input_schema": {
        "type": "object",
        "properties": {
            "hook": {
                "type": "string",
                "description": "The opening line/moment that grabs attention in the first second.",
            },
            "shot_list": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Concrete, ordered shots/beats to capture or design.",
            },
            "visual_references": {
                "type": "string",
                "description": "Visual style, mood, color, or reference direction.",
            },
            "editing_notes": {
                "type": "string",
                "description": "Pacing, transitions, captions, music/sound direction.",
            },
            "thumbnail_concept": {
                "type": "string",
                "description": (
                    "A thumbnail/cover concept, only for video-style content. "
                    "Empty string if not applicable."
                ),
            },
        },
        "required": ["hook", "shot_list", "visual_references", "editing_notes"],
    },
}


@dataclass(slots=True)
class GeneratedCreativeBrief:
    hook: str | None = None
    shot_list: list[str] = field(default_factory=list)
    visual_references: str | None = None
    editing_notes: str | None = None
    thumbnail_concept: str | None = None


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def generate_creative_brief(
    context: str, title: str, description: str, platform: str, content_type: str
) -> tuple[GeneratedCreativeBrief, bool]:
    """Never raises — returns `(GeneratedCreativeBrief(), False)` on any
    failure, same graceful-degradation contract as every other generator
    in this codebase."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping creative brief generation")
        return GeneratedCreativeBrief(), False

    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=1536,
            system=_SYSTEM_PROMPT,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "generate_creative_brief"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"{context}\n\n"
                        f"Platform: {platform}\n"
                        f"Content type: {content_type}\n"
                        f"Title: {title}\n"
                        f"Description: {description}\n\n"
                        "Use the `generate_creative_brief` tool."
                    ),
                }
            ],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        data = tool_use.input
    except Exception:
        logger.exception("Claude creative brief generation failed")
        return GeneratedCreativeBrief(), False

    return (
        GeneratedCreativeBrief(
            hook=data.get("hook"),
            shot_list=data.get("shot_list") or [],
            visual_references=data.get("visual_references"),
            editing_notes=data.get("editing_notes"),
            thumbnail_concept=data.get("thumbnail_concept") or None,
        ),
        True,
    )
