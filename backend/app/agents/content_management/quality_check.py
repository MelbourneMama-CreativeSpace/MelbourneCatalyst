"""Claude-powered content quality review + brand consistency check — one
call, one feature, not two systems: brand-voice adherence is a dimension
of quality review, not a separate checker. Same one-shot forced-tool
pattern as `strategy.py`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from anthropic import AsyncAnthropic

from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"

_SYSTEM_PROMPT = (
    "You are reviewing a social media post before it goes out — not writing "
    "one. Check grammar, readability, formatting, and whether the tone "
    "actually matches the brand voice given. Be specific and concrete about "
    "issues; don't invent problems that aren't there, and don't nitpick "
    "stylistic choices that are clearly intentional for the platform."
)

_TOOL = {
    "name": "check_content_quality",
    "description": "Review a piece of content for quality and brand-voice consistency.",
    "input_schema": {
        "type": "object",
        "properties": {
            "passed": {
                "type": "boolean",
                "description": "True if the content is ready to publish as-is.",
            },
            "issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Specific, concrete issues found (grammar, tone mismatch, "
                    "formatting, off-brand language). Empty array if none."
                ),
            },
            "notes": {
                "type": "string",
                "description": "One or two sentences summarizing the overall assessment.",
            },
        },
        "required": ["passed", "issues", "notes"],
    },
}


@dataclass(slots=True)
class QualityCheckResult:
    passed: bool | None = None
    issues: list[str] = field(default_factory=list)
    notes: str | None = None


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def check_content_quality(
    draft_copy: str, brand_voice: str | None, platform: str
) -> tuple[QualityCheckResult, bool]:
    """Never raises — returns `(QualityCheckResult(), False)` on any
    failure, same graceful-degradation contract as every other generator
    in this codebase."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping quality check")
        return QualityCheckResult(), False

    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "check_content_quality"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Platform: {platform}\n"
                        f"Brand voice: {brand_voice or 'not specified'}\n\n"
                        f"Content to review:\n{draft_copy}\n\n"
                        "Use the `check_content_quality` tool."
                    ),
                }
            ],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        data = tool_use.input
    except Exception:
        logger.exception("Claude quality check failed")
        return QualityCheckResult(), False

    return (
        QualityCheckResult(
            passed=data.get("passed"),
            issues=data.get("issues") or [],
            notes=data.get("notes"),
        ),
        True,
    )
