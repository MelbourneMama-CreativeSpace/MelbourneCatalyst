"""Claude-powered Knowledge Base audit report generation.

Same shape as `content_management/strategy.py` — forced tool-use call
over a pre-formatted context string (company profile + a sample of that
company's ingested document content, built by the graph's
`gather_context` node).
"""

from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from app.agents.knowledge_base.schemas import GeneratedAudit
from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"
_MAX_CONTEXT_CHARS = 100_000

_TOOL = {
    "name": "generate_audit",
    "description": (
        "Audit a company's Knowledge Base — what it currently covers, what's "
        "missing, and what to add next — based on its profile and a sample of its "
        "ingested document content."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "coverage_summary": {
                "type": "string",
                "description": "What topics/areas the current knowledge base actually covers",
            },
            "identified_gaps": {
                "type": "string",
                "description": "What's missing or thin, relative to what this company would need documented",
            },
            "recommendations": {
                "type": "string",
                "description": "Concrete next sources/documents to add to close the gaps",
            },
        },
        "required": ["coverage_summary", "identified_gaps"],
    },
}


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def generate_audit(context: str) -> tuple[GeneratedAudit, bool]:
    """Call Claude to generate a KB audit from `context` (company profile
    + a sample of ingested document content, pre-formatted by the
    caller). Never raises — returns `(GeneratedAudit(), False)` on any
    failure so the graph can persist a `failed` row with a clear
    status_error instead of a 500."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping knowledge audit generation")
        return GeneratedAudit(), False

    trimmed = context[:_MAX_CONTEXT_CHARS]
    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=2048,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "generate_audit"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Generate a knowledge base audit using the `generate_audit` "
                        f"tool from this context:\n\n{trimmed}"
                    ),
                }
            ],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        data = tool_use.input
    except Exception:
        logger.exception("Claude knowledge audit generation failed")
        return GeneratedAudit(), False

    audit = GeneratedAudit(
        coverage_summary=data.get("coverage_summary"),
        identified_gaps=data.get("identified_gaps"),
        recommendations=data.get("recommendations"),
    )
    return audit, True
