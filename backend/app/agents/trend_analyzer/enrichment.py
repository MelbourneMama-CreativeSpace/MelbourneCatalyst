"""Claude-powered enrichment: categorize + one-line insight per new trend item.

Batches every new item from a collection run into as few Anthropic calls as
practical (chunks of `_BATCH_SIZE`) rather than one call per item — this is
the main lever for keeping token spend down, on top of only ever enriching
items the `merge_and_dedupe` graph node has confirmed are new.
"""

from __future__ import annotations

import logging

from anthropic import AsyncAnthropic

from app.agents.trend_analyzer.schemas import EnrichedTrendItem, RawTrendItem
from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-5"
_BATCH_SIZE = 25
_FALLBACK_CATEGORY = "uncategorized"

CATEGORIES = [
    "marketing",
    "technology",
    "business",
    "entertainment",
    "lifestyle",
    "sports",
    "politics",
    "health",
    "other",
]

_TOOL = {
    "name": "categorize_trends",
    "description": "Categorize a batch of trend items and give a one-sentence insight for each.",
    "input_schema": {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {
                            "type": "integer",
                            "description": "0-based index matching the input item order",
                        },
                        "category": {"type": "string", "enum": CATEGORIES},
                        "insight": {
                            "type": "string",
                            "description": "One short sentence on why this trend matters",
                        },
                    },
                    "required": ["index", "category", "insight"],
                },
            }
        },
        "required": ["results"],
    },
}


def _client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)


def _chunks(items: list[RawTrendItem], size: int) -> list[list[RawTrendItem]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _build_prompt(batch: list[RawTrendItem]) -> str:
    lines = [
        f"{i}. [{item.source.value}] {item.title} — {(item.description or '')[:200]}"
        for i, item in enumerate(batch)
    ]
    return (
        "Categorize each of the following trending items using the "
        "`categorize_trends` tool. Give a one-sentence insight explaining why "
        "each trend might matter to a marketing team.\n\n" + "\n".join(lines)
    )


async def enrich_items(items: list[RawTrendItem]) -> list[EnrichedTrendItem]:
    """Categorize and annotate new trend items. Never raises — falls back to
    an "uncategorized" placeholder per item on any batch failure so a single
    LLM error doesn't drop otherwise-valid trends from the run."""
    if not items:
        return []
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not configured; skipping trend enrichment")
        return [_fallback(item) for item in items]

    client = _client()
    enriched: list[EnrichedTrendItem] = []
    for batch in _chunks(items, _BATCH_SIZE):
        enriched.extend(await _enrich_batch(client, batch))
    return enriched


async def _enrich_batch(
    client: AsyncAnthropic, batch: list[RawTrendItem]
) -> list[EnrichedTrendItem]:
    try:
        response = await client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "categorize_trends"},
            messages=[{"role": "user", "content": _build_prompt(batch)}],
        )
        tool_use = next(block for block in response.content if block.type == "tool_use")
        results = {r["index"]: r for r in tool_use.input["results"]}
    except Exception:
        logger.exception("Claude enrichment failed for a batch of %d items", len(batch))
        return [_fallback(item) for item in batch]

    return [
        EnrichedTrendItem(
            item=item,
            category=results.get(i, {}).get("category", _FALLBACK_CATEGORY),
            insight=results.get(i, {}).get("insight", ""),
        )
        for i, item in enumerate(batch)
    ]


def _fallback(item: RawTrendItem) -> EnrichedTrendItem:
    return EnrichedTrendItem(item=item, category=_FALLBACK_CATEGORY, insight="")
