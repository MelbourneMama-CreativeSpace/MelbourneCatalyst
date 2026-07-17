"""Claude-powered company profile extraction.

Mirrors `trend_analyzer/enrichment.py`: Anthropic Messages API with a
forced tool call that returns a structured JSON matching the
`CompanyProfile` schema. Kept as a single call over aggregated
website content — a company profile fits comfortably in Claude's
context, and one call is cheaper than orchestrating per-field prompts.
"""

from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from app.agents.company_analyzer.schemas import CompanyProfile
from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"
# ~150k chars of input is well below Claude Sonnet's 200k-token window even
# after we prepend a system prompt; truncate aggressively so a very large
# website doesn't push us into paginated tool-use territory.
_MAX_CONTENT_CHARS = 150_000

_TOOL = {
    "name": "extract_company_profile",
    "description": "Extract a structured business profile from the given website content.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "The company or organization name"},
            "industry": {
                "type": "string",
                "description": "Primary industry (e.g. 'B2B SaaS', 'Non-profit', 'DTC apparel')",
            },
            "business_model": {
                "type": "string",
                "description": "How the business generates revenue in one sentence",
            },
            "target_audience": {
                "type": "string",
                "description": "Ideal customer profile — demographics, needs, context",
            },
            "brand_voice": {
                "type": "string",
                "description": "Tone and personality of the brand's communication",
            },
            "unique_value_prop": {
                "type": "string",
                "description": "What makes this company unique in the market",
            },
            "niche_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "5-15 short keywords/phrases that define the company's niche, used for relevance-scoring trends",
            },
            "summary": {
                "type": "string",
                "description": "One-paragraph overview of the company",
            },
        },
        "required": ["niche_keywords"],
    },
}


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


async def extract_company_profile(website_content: str) -> CompanyProfile:
    """Call Claude to extract a structured profile. Never raises — returns a
    mostly-empty CompanyProfile on any failure so onboarding still completes
    (the row can be edited manually later)."""
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping company profile extraction")
        return CompanyProfile()

    trimmed = website_content[:_MAX_CONTENT_CHARS]
    try:
        response = await _client().messages.create(
            model=_MODEL,
            max_tokens=2048,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "extract_company_profile"},
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Extract a structured company profile using the "
                        "`extract_company_profile` tool from this website content:\n\n"
                        f"{trimmed}"
                    ),
                }
            ],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        data = tool_use.input
    except Exception:
        logger.exception("Claude company profile extraction failed")
        return CompanyProfile()

    return CompanyProfile(
        name=data.get("name"),
        industry=data.get("industry"),
        business_model=data.get("business_model"),
        target_audience=data.get("target_audience"),
        brand_voice=data.get("brand_voice"),
        unique_value_prop=data.get("unique_value_prop"),
        niche_keywords=list(data.get("niche_keywords") or []),
        summary=data.get("summary"),
    )
