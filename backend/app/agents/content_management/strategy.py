"""Claude-powered marketing strategy generation.

Mirrors `company_analyzer/extractor.py` exactly: Anthropic Messages API
with a forced tool call, takes a single pre-formatted context string (built
by the graph's `gather_context` node from the company profile + currently
relevant trends) rather than raw ORM objects — keeps this module testable
without a DB dependency, same as the extractor.
"""

from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from app.agents.content_management.schemas import GeneratedStrategy
from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"
_MAX_CONTEXT_CHARS = 100_000

_TOOL = {
    "name": "generate_marketing_strategy",
    "description": (
        "Generate a marketing strategy based on a company's profile and the "
        "trends currently most relevant to it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "One-paragraph overview of the recommended strategy",
            },
            "marketing_strategy": {
                "type": "string",
                "description": "Marketing strategy aligned with the company's business objectives",
            },
            "campaign_direction": {
                "type": "string",
                "description": "Campaign direction and creative brief ideas, tied to the relevant trends given",
            },
            "growth_recommendations": {
                "type": "string",
                "description": "Growth recommendations grounded in the company's current position",
            },
            "business_suggestions": {
                "type": "string",
                "description": "Business suggestions for market positioning",
            },
        },
        "required": ["summary", "marketing_strategy"],
    },
}


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def generate_strategy(context: str) -> tuple[GeneratedStrategy, bool]:
    """Call Claude to generate a strategy from `context` (company profile +
    relevant trends, pre-formatted by the caller). Never raises — returns
    `(GeneratedStrategy(), False)` on any failure so the graph can persist a
    `failed` Strategy row with a clear status_error instead of a 500."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping strategy generation")
        return GeneratedStrategy(), False

    trimmed = context[:_MAX_CONTEXT_CHARS]
    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=2048,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "generate_marketing_strategy"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Generate a marketing strategy using the "
                        "`generate_marketing_strategy` tool from this context:\n\n"
                        f"{trimmed}"
                    ),
                }
            ],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        data = tool_use.input
    except Exception:
        logger.exception("Claude strategy generation failed")
        return GeneratedStrategy(), False

    strategy = GeneratedStrategy(
        summary=data.get("summary"),
        marketing_strategy=data.get("marketing_strategy"),
        campaign_direction=data.get("campaign_direction"),
        growth_recommendations=data.get("growth_recommendations"),
        business_suggestions=data.get("business_suggestions"),
    )
    return strategy, True
