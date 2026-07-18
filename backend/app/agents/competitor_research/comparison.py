"""Claude-powered Company-vs-Competitor comparison generation.

Same shape as `content_management/strategy.py` — forced tool-use call
over a pre-formatted context string (both companies' profiles, built by
the graph's `gather_context` node).
"""

from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from app.agents.competitor_research.schemas import GeneratedComparison
from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"
_MAX_CONTEXT_CHARS = 100_000

_TOOL = {
    "name": "generate_comparison",
    "description": (
        "Compare a company against a competitor based on both of their profiles, "
        "producing a practical competitive analysis."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "product_pricing_comparison": {
                "type": "string",
                "description": "How the two companies' products/services and likely pricing/positioning compare",
            },
            "marketing_strategy_analysis": {
                "type": "string",
                "description": "How the competitor markets itself, and what that suggests about their strategy",
            },
            "competitive_gaps": {
                "type": "string",
                "description": "Where the company is weaker or missing something relative to the competitor",
            },
            "strategic_recommendations": {
                "type": "string",
                "description": "Concrete actions the company could take in response to this competitor",
            },
        },
        "required": ["product_pricing_comparison", "competitive_gaps"],
    },
}


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def generate_comparison(context: str) -> tuple[GeneratedComparison, bool]:
    """Call Claude to generate a comparison from `context` (both companies'
    profiles, pre-formatted by the caller). Never raises — returns
    `(GeneratedComparison(), False)` on any failure so the graph can persist
    a `failed` comparison with a clear status_error instead of a 500."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping comparison generation")
        return GeneratedComparison(), False

    trimmed = context[:_MAX_CONTEXT_CHARS]
    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=2048,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "generate_comparison"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Generate a competitive comparison using the "
                        f"`generate_comparison` tool from this context:\n\n{trimmed}"
                    ),
                }
            ],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        data = tool_use.input
    except Exception:
        logger.exception("Claude comparison generation failed")
        return GeneratedComparison(), False

    comparison = GeneratedComparison(
        product_pricing_comparison=data.get("product_pricing_comparison"),
        marketing_strategy_analysis=data.get("marketing_strategy_analysis"),
        competitive_gaps=data.get("competitive_gaps"),
        strategic_recommendations=data.get("strategic_recommendations"),
    )
    return comparison, True
