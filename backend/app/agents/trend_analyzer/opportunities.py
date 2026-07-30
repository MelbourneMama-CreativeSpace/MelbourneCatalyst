"""Content Opportunity Discovery — one Claude call producing a ranked list
of concrete opportunities with a stated reason each, grounded in a
company's own real data (its relevance-scored trends, upcoming seasonal
dates, and — once any exist — its own performance snapshots). Not a new
scoring subsystem: folds trend relevance + seasonal matching + real
performance signal into one generation, same "one Claude call, not raw
similarity numbers with no actionable meaning" shape as `report.py`.
"""

from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from app.agents.trend_analyzer.schemas import GeneratedOpportunity
from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"
_MAX_CONTEXT_CHARS = 100_000

_TOOL = {
    "name": "generate_content_opportunities",
    "description": "Produce a ranked list of concrete content opportunities for a company, each with a stated reason.",
    "input_schema": {
        "type": "object",
        "properties": {
            "opportunities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "A specific, actionable content opportunity — not a vague theme.",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Why this is an opportunity right now, grounded in the actual data given.",
                        },
                        "source": {
                            "type": "string",
                            "enum": ["trend", "seasonal", "performance", "evergreen"],
                            "description": (
                                "What this opportunity is grounded in: a specific trend given, an "
                                "upcoming seasonal date given, this company's own performance data "
                                "given, or a genuinely evergreen idea with no specific trigger."
                            ),
                        },
                        "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["title", "reasoning", "source", "priority"],
                },
            }
        },
        "required": ["opportunities"],
    },
}


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def generate_content_opportunities(context: str) -> tuple[list[GeneratedOpportunity], bool]:
    """Never raises — returns `([], False)` on any failure, same
    graceful-degradation contract as every other generator here."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping opportunity generation")
        return [], False

    trimmed = context[:_MAX_CONTEXT_CHARS]
    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=2048,
            system=(
                "You surface concrete, actionable content opportunities for a company, "
                "grounded strictly in the real data given — its own scored trends, upcoming "
                "seasonal dates, and (if given) its own recent performance data. Every "
                "opportunity must cite what it's grounded in via the `source` field. Don't "
                "invent trends or performance signals that aren't in the context; an "
                "'evergreen' opportunity with no specific trigger is fine and honest when "
                "the data given doesn't support anything more specific."
            ),
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "generate_content_opportunities"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Generate a ranked list of content opportunities using the "
                        f"`generate_content_opportunities` tool from this context:\n\n{trimmed}"
                    ),
                }
            ],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        raw_items = tool_use.input.get("opportunities", [])
    except Exception:
        logger.exception("Claude content opportunity generation failed")
        return [], False

    opportunities = []
    for raw in raw_items:
        try:
            opportunities.append(
                GeneratedOpportunity(
                    title=raw["title"],
                    reasoning=raw["reasoning"],
                    source=raw["source"],
                    priority=raw["priority"],
                )
            )
        except KeyError:
            # Malformed item from the model — skip it rather than losing
            # the whole list to one bad entry, same pattern as
            # content_planner.py's generate_content_plan.
            continue
    return opportunities, True
