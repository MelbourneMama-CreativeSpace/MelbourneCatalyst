"""Claude-powered brand collaboration ideation.

Same shape as `content_planner.py` — forced tool-use call producing a list
of ideas. Each idea is a collaborator *archetype* ("micro-influencer food
bloggers, 5-20k followers, Melbourne-based"), not a named real account —
there's no live social search available to find actual candidates, and
inventing fake names would be worse than being honest about that gap.
`priority`/ROI here is Claude's qualitative estimate, not a computed
prediction — there's no historical campaign performance data to compute
one from.
"""

from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from app.agents.content_management.schemas import GeneratedCollaboration, GeneratedCollaborationIdea
from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"
_MAX_CONTEXT_CHARS = 100_000

_PRIORITIES = ["low", "medium", "high"]

_TOOL = {
    "name": "generate_collaboration",
    "description": (
        "Generate brand collaboration/partnership ideas based on a company's profile "
        "and marketing strategy. Describe collaborator archetypes (audience/niche/scale), "
        "not named real people or accounts — none are being looked up live."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "ideas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "collaborator_archetype": {
                            "type": "string",
                            "description": "The type of collaborator to target, e.g. 'micro-influencer food bloggers, 5-20k followers, Melbourne-based'",
                        },
                        "partnership_angle": {
                            "type": "string",
                            "description": "What the partnership would actually involve and why it fits this company",
                        },
                        "outreach_template": {
                            "type": "string",
                            "description": "A short draft outreach message for this kind of collaborator",
                        },
                        "priority": {"type": "string", "enum": _PRIORITIES},
                        "rationale": {
                            "type": "string",
                            "description": "Why this is a good fit and roughly how valuable it could be — qualitative, not a computed number",
                        },
                    },
                    "required": [
                        "collaborator_archetype",
                        "partnership_angle",
                        "outreach_template",
                        "priority",
                    ],
                },
            }
        },
        "required": ["ideas"],
    },
}


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def generate_collaboration(context: str) -> tuple[GeneratedCollaboration, bool]:
    """Call Claude to generate collaboration ideas from `context` (company
    profile + optional strategy + relevant trends, pre-formatted by the
    caller). Never raises — returns `(GeneratedCollaboration(), False)` on
    any failure."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping collaboration generation")
        return GeneratedCollaboration(), False

    trimmed = context[:_MAX_CONTEXT_CHARS]
    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=3072,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "generate_collaboration"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Generate up to {settings.COLLABORATION_MAX_IDEAS} brand collaboration "
                        "ideas using the `generate_collaboration` tool from this context:\n\n"
                        f"{trimmed}"
                    ),
                }
            ],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        raw_ideas = tool_use.input.get("ideas", [])
    except Exception:
        logger.exception("Claude collaboration generation failed")
        return GeneratedCollaboration(), False

    ideas = []
    for raw in raw_ideas[: settings.COLLABORATION_MAX_IDEAS]:
        try:
            priority = raw["priority"]
            ideas.append(
                GeneratedCollaborationIdea(
                    collaborator_archetype=raw["collaborator_archetype"],
                    partnership_angle=raw["partnership_angle"],
                    outreach_template=raw["outreach_template"],
                    priority=priority if priority in _PRIORITIES else "medium",
                    rationale=raw.get("rationale") or None,
                )
            )
        except (KeyError, TypeError):
            # Malformed idea from the model — skip it rather than losing
            # the whole batch to one bad entry.
            continue
    return GeneratedCollaboration(ideas=ideas), True
