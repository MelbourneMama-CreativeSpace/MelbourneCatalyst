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

# Fixed-date (non-movable) commercial/awareness dates worth planning content
# around. Deliberately excludes movable-date events (Easter, Mother's/
# Father's Day, Black Friday) since those shift year to year and this table
# has no year-awareness — a wrong date would be worse than no suggestion.
_SEASONAL_EVENTS: dict[tuple[int, int], str] = {
    (1, 1): "New Year's Day",
    (2, 14): "Valentine's Day",
    (3, 8): "International Women's Day",
    (4, 22): "Earth Day",
    (5, 1): "International Workers' Day",
    (6, 5): "World Environment Day",
    (10, 31): "Halloween",
    (12, 25): "Christmas",
    (12, 31): "New Year's Eve",
}


def _seasonal_candidates(start: date, days: int) -> list[str]:
    """Fixed-date seasonal/awareness events falling within [start, start+days)."""
    candidates = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        event = _SEASONAL_EVENTS.get((day.month, day.day))
        if event:
            candidates.append(f"{event} ({day.isoformat()})")
    return candidates


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
                            "description": "A one-line brief of what the content shows/covers — for the calendar view, not the post itself",
                        },
                        "draft_copy": {
                            "type": "string",
                            "description": (
                                "The actual finished, ready-to-publish copy for this post — not a "
                                "brief or an outline. Write it the way it should actually appear: "
                                "full caption text in the platform's real voice and length "
                                "conventions (e.g. a punchy hook + body + call-to-action for "
                                "Instagram/TikTok, a professional framing for LinkedIn, concise for "
                                "X/Twitter), including hashtags where that platform's audience "
                                "expects them. Someone should be able to copy this verbatim and post "
                                "it, not rewrite it first."
                            ),
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
                        "audience_interest": {
                            "type": "string",
                            "description": (
                                "Which audience segment or interest (from the company's target "
                                "audience/niche keywords) this idea speaks to — empty string if "
                                "generically aimed at the whole audience"
                            ),
                        },
                        "seasonal_event": {
                            "type": "string",
                            "description": (
                                "The exact seasonal/awareness event name (from the candidates given "
                                "in context) this idea ties to, if any — empty string if none. Only "
                                "use one of the given candidates, never invent a date."
                            ),
                        },
                    },
                    "required": [
                        "title",
                        "description",
                        "draft_copy",
                        "content_type",
                        "platform",
                        "days_from_now",
                    ],
                },
            }
        },
        "required": ["items"],
    },
}


_REGEN_TOOL = {
    "name": "regenerate_draft_copy",
    "description": "Rewrite the ready-to-publish draft copy for a single content calendar item.",
    "input_schema": {
        "type": "object",
        "properties": {
            "draft_copy": {
                "type": "string",
                "description": (
                    "The actual finished, ready-to-publish copy for this post — not a brief "
                    "or an outline. Full caption text in the platform's real voice and length "
                    "conventions, including hashtags where that platform's audience expects "
                    "them. Someone should be able to copy this verbatim and post it."
                ),
            }
        },
        "required": ["draft_copy"],
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

    today = date.today()
    seasonal_candidates = _seasonal_candidates(today, days)
    seasonal_context = (
        "\n\n# Seasonal/awareness dates in this window (tie ideas to these only if genuinely relevant)\n"
        + "\n".join(f"- {c}" for c in seasonal_candidates)
        if seasonal_candidates
        else ""
    )

    trimmed = context[:_MAX_CONTEXT_CHARS] + seasonal_context
    try:
        response = await _client().messages.create(
            model=_MODEL,
            # Each item now carries full publishable copy, not just a
            # one-line brief — a 30-day plan's worth of real captions needs
            # meaningfully more room than the old title/description-only
            # shape did.
            max_tokens=8192,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "generate_content_plan"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Generate a {days}-day content calendar using the "
                        "`generate_content_plan` tool from this context. For every item, "
                        "`draft_copy` must be finished, ready-to-publish post text — not a "
                        "summary or an outline:\n\n"
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
                    audience_interest=raw.get("audience_interest") or None,
                    seasonal_event=raw.get("seasonal_event") or None,
                    # A required field — if the model omits it, skip this
                    # item entirely (via the except below) rather than
                    # silently persisting a slot with no draft, which would
                    # just reintroduce the "spec, not a draft" gap.
                    draft_copy=raw["draft_copy"],
                )
            )
        except (KeyError, TypeError, ValueError):
            # Malformed item from the model (missing/wrong-typed field) —
            # skip it rather than losing the whole plan to one bad entry.
            continue
    return GeneratedContentPlan(items=items), True


async def regenerate_draft_copy(
    context: str, title: str, description: str, content_type: str, platform: str
) -> tuple[str | None, bool]:
    """Rewrite just the `draft_copy` for one existing calendar item — the
    UI's "regenerate" action when a draft needs another pass, rather than
    a full plan regeneration. Never raises — returns `(None, False)` on
    any failure."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping draft copy regeneration")
        return None, False

    trimmed = context[:_MAX_CONTEXT_CHARS]
    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=1024,
            tools=[_REGEN_TOOL],
            tool_choice={"type": "tool", "name": "regenerate_draft_copy"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Write ready-to-publish {platform} {content_type} copy for the "
                        f'calendar item titled "{title}" — brief: {description}. Use the '
                        "`regenerate_draft_copy` tool. Company/strategy context:\n\n"
                        f"{trimmed}"
                    ),
                }
            ],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        draft_copy = tool_use.input.get("draft_copy")
    except Exception:
        logger.exception("Claude draft copy regeneration failed")
        return None, False

    if not draft_copy:
        return None, False
    return draft_copy, True
