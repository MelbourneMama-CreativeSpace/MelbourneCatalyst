"""Claude-powered trend report generation.

Same shape as `content_management/strategy.py` — forced tool-use call
over a pre-formatted context string (company profile + recent
relevance-scored trends, built by the graph's `gather_context` node).
Covers three TODO.md checklist items (weekly market report, industry
insights summarizer, content opportunity recommender) as three sections
of one generation rather than three separate Claude calls.
"""

from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from app.agents.trend_analyzer.schemas import GeneratedTrendReport
from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"
_MAX_CONTEXT_CHARS = 100_000

_TOOL = {
    "name": "generate_trend_report",
    "description": (
        "Generate a market trend report for a company based on its profile and the "
        "trends currently most relevant to it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "One-paragraph overview of the period's trend landscape for this company",
            },
            "key_themes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-6 short theme labels that summarize what's trending in this space",
            },
            "notable_trends_summary": {
                "type": "string",
                "description": "The most noteworthy individual trends and why they matter",
            },
            "content_opportunities": {
                "type": "string",
                "description": "Concrete content/marketing opportunities this company could act on given these trends",
            },
        },
        "required": ["summary", "key_themes"],
    },
}


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def generate_trend_report(context: str) -> tuple[GeneratedTrendReport, bool]:
    """Call Claude to generate a trend report from `context` (company
    profile + recent relevant trends, pre-formatted by the caller). Never
    raises — returns `(GeneratedTrendReport(), False)` on any failure so
    the graph can persist a `failed` row with a clear status_error
    instead of a 500."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping trend report generation")
        return GeneratedTrendReport(), False

    trimmed = context[:_MAX_CONTEXT_CHARS]
    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=2048,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "generate_trend_report"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Generate a trend report using the `generate_trend_report` "
                        f"tool from this context:\n\n{trimmed}"
                    ),
                }
            ],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        data = tool_use.input
    except Exception:
        logger.exception("Claude trend report generation failed")
        return GeneratedTrendReport(), False

    report = GeneratedTrendReport(
        summary=data.get("summary"),
        key_themes=list(data.get("key_themes") or []),
        notable_trends_summary=data.get("notable_trends_summary"),
        content_opportunities=data.get("content_opportunities"),
    )
    return report, True
