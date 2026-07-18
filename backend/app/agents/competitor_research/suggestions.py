"""Claude-suggested competitor names.

Not a live discovery tool — Claude has no web access here, so this can
only draw on its training knowledge. Returns candidate company *names*
for the user to research and manually onboard by URL; never returns URLs
itself, since it can't verify one currently exists or is correct.
"""

from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"
_MAX_CONTEXT_CHARS = 20_000

_TOOL = {
    "name": "suggest_competitor_names",
    "description": (
        "Suggest likely competitor company names for the given business, based on "
        "general knowledge. Names only — no URLs, since none are being verified live."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-8 likely competitor company names",
            }
        },
        "required": ["names"],
    },
}


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def suggest_competitor_names(context: str) -> tuple[list[str], bool]:
    """Call Claude to suggest competitor names from `context` (the
    company's profile, pre-formatted by the caller). Never raises —
    returns `([], False)` on any failure."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping competitor suggestions")
        return [], False

    trimmed = context[:_MAX_CONTEXT_CHARS]
    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=512,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "suggest_competitor_names"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Suggest likely competitor names using the "
                        f"`suggest_competitor_names` tool for this business:\n\n{trimmed}"
                    ),
                }
            ],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        names = tool_use.input.get("names", [])
    except Exception:
        logger.exception("Claude competitor suggestion failed")
        return [], False

    return [name for name in names if isinstance(name, str) and name.strip()], True
