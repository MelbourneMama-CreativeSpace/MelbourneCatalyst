"""Claude-powered campaign plan generation.

Same shape as `strategy.py` — forced tool-use call over a pre-formatted
context string (company profile + optional strategy + optional content
plan date range + relevant trends). `start_date`/`end_date` are asked as
ISO date strings (Claude is good at these when a concrete anchor date is
given in the context, unlike relative day offsets which risk
hallucination for a single date range).
"""

from __future__ import annotations

import logging
from datetime import date

from anthropic import AsyncAnthropic

from app.agents.content_management.schemas import GeneratedCampaign
from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"
_MAX_CONTEXT_CHARS = 100_000

_TOOL = {
    "name": "generate_campaign",
    "description": "Generate a marketing campaign plan based on a company's profile, its marketing strategy, and its content calendar.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "A short, memorable campaign name"},
            "objective": {
                "type": "string",
                "description": "What this campaign is trying to achieve, tied to the company's strategy",
            },
            "budget_allocation": {
                "type": "string",
                "description": "A recommended budget split across platforms/content types — a suggestion, not a real number based on live ad spend data",
            },
            "success_metrics": {
                "type": "string",
                "description": "KPIs to track for this campaign",
            },
            "start_date": {
                "type": "string",
                "description": "ISO date (YYYY-MM-DD) the campaign should start — align with the content calendar's date range if one was given",
            },
            "end_date": {
                "type": "string",
                "description": "ISO date (YYYY-MM-DD) the campaign should end",
            },
        },
        "required": ["name", "objective"],
    },
}


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


def _parse_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


async def generate_campaign(context: str) -> tuple[GeneratedCampaign, bool]:
    """Call Claude to generate a campaign plan from `context` (company
    profile + optional strategy/content-plan timeline + relevant trends,
    pre-formatted by the caller). Never raises — returns
    `(GeneratedCampaign(), False)` on any failure so the graph can persist a
    `failed` Campaign row with a clear status_error instead of a 500."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping campaign generation")
        return GeneratedCampaign(), False

    trimmed = context[:_MAX_CONTEXT_CHARS]
    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=1536,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "generate_campaign"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Generate a campaign plan using the `generate_campaign` "
                        f"tool from this context:\n\n{trimmed}"
                    ),
                }
            ],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        data = tool_use.input
    except Exception:
        logger.exception("Claude campaign generation failed")
        return GeneratedCampaign(), False

    campaign = GeneratedCampaign(
        name=data.get("name"),
        objective=data.get("objective"),
        budget_allocation=data.get("budget_allocation"),
        success_metrics=data.get("success_metrics"),
        start_date=_parse_date(data.get("start_date")),
        end_date=_parse_date(data.get("end_date")),
    )
    return campaign, True
