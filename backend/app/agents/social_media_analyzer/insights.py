"""Content Insights & Recommendations — one Claude call reasoning over a
company's own stored performance data (metric snapshots + recently
published content). Same one-shot forced-tool pattern as every other
generator in this codebase. The one thing this module is strict about:
never speculate when the data is thin or empty — the system prompt
explicitly asks for a plain "not enough data yet" instead of a
plausible-sounding fabrication, since the entire point of "insights" is
claiming something true about real performance.
"""

from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"

_SYSTEM_PROMPT = (
    "You analyze a company's own social media performance data — recent "
    "metric snapshots (followers, engagement) and recently published "
    "content — to surface concrete insights and recommendations. If the "
    "data given is too thin or empty to say anything real, say so plainly "
    "and explain what's missing (e.g. \"not enough data yet — only one "
    "metric snapshot exists\") rather than inventing plausible-sounding "
    "insights. Never speculate beyond what the data actually shows."
)

_TOOL = {
    "name": "generate_performance_insights",
    "description": "Analyze a company's real performance data and produce insights/recommendations.",
    "input_schema": {
        "type": "object",
        "properties": {
            "insights": {
                "type": "string",
                "description": (
                    "Concrete insights and recommendations grounded in the data given, "
                    "or a plain statement that there isn't enough data yet if so."
                ),
            },
        },
        "required": ["insights"],
    },
}


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def generate_performance_insights(context: str) -> tuple[str | None, bool]:
    """Never raises — returns `(None, False)` on any failure, same
    graceful-degradation contract as every other generator here."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping performance insights generation")
        return None, False

    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "generate_performance_insights"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"{context}\n\nUse the `generate_performance_insights` tool."
                    ),
                }
            ],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        insights = tool_use.input.get("insights")
    except Exception:
        logger.exception("Claude performance insights generation failed")
        return None, False

    if not insights:
        return None, False
    return insights, True
