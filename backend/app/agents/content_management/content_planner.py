"""Claude-powered content calendar generation.

Same shape as `strategy.py` — forced tool-use call over a pre-formatted
context string. The tool asks Claude for `days_from_now` (an integer
offset) per item rather than an absolute date, which avoids date-format
hallucination entirely; this module converts that to a real `date` here so
the graph's persist node just writes it straight to the DB.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from anthropic import AsyncAnthropic

from app.agents.content_management.schemas import GeneratedContentItem, GeneratedContentPlan
from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"
_MAX_CONTEXT_CHARS = 100_000

_CONTENT_TYPES = ["post", "video", "article", "carousel", "story"]
_PLATFORMS = ["instagram", "linkedin", "twitter", "tiktok", "youtube", "blog", "facebook"]

_TOOL = {
    "name": "generate_content_plan",
    "description": "Generate a content calendar of specific, publishable content ideas.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {
                            "type": "string",
                            "description": "What the content actually says/shows — specific enough to brief a writer",
                        },
                        "content_type": {"type": "string", "enum": _CONTENT_TYPES},
                        "platform": {"type": "string", "enum": _PLATFORMS},
                        "theme": {
                            "type": "string",
                            "description": "Short theme/campaign tag this idea belongs to",
                        },
                        "days_from_now": {
                            "type": "integer",
                            "description": "How many days from today this should publish (0 = today)",
                        },
                        "related_trend_title": {
                            "type": "string",
                            "description": (
                                "The exact title of the trend (from the context given) this idea "
                                "was inspired by, if any — empty string if none"
                            ),
                        },
                    },
                    "required": ["title", "description", "content_type", "platform", "days_from_now"],
                },
            }
        },
        "required": ["items"],
    },
}


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def generate_content_plan(context: str, days: int) -> tuple[GeneratedContentPlan, bool]:
    """Call Claude to generate a `days`-day content calendar from `context`
    (company profile + optional strategy + relevant trends, pre-formatted
    by the caller). Never raises — returns `(GeneratedContentPlan(), False)`
    on any failure."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping content plan generation")
        return GeneratedContentPlan(), False

    trimmed = context[:_MAX_CONTEXT_CHARS]
    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=4096,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "generate_content_plan"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Generate a {days}-day content calendar using the "
                        "`generate_content_plan` tool from this context:\n\n"
                        f"{trimmed}"
                    ),
                }
            ],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        raw_items = tool_use.input.get("items", [])
    except Exception:
        logger.exception("Claude content plan generation failed")
        return GeneratedContentPlan(), False

    today = date.today()
    items = []
    for raw in raw_items:
        try:
            days_from_now = max(0, min(int(raw.get("days_from_now", 0)), days - 1))
            items.append(
                GeneratedContentItem(
                    title=raw["title"],
                    description=raw["description"],
                    content_type=raw["content_type"],
                    platform=raw["platform"],
                    suggested_date=today + timedelta(days=days_from_now),
                    theme=raw.get("theme") or None,
                    related_trend_title=raw.get("related_trend_title") or None,
                )
            )
        except (KeyError, TypeError, ValueError):
            # Malformed item from the model (missing/wrong-typed field) —
            # skip it rather than losing the whole plan to one bad entry.
            continue
    return GeneratedContentPlan(items=items), True
