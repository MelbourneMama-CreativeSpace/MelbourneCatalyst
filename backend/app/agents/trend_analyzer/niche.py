"""The active niche, resolved from onboarded companies instead of .env.

Every collector used to carry its own hard-coded keyword list
(`GOOGLE_TRENDS_SEED_KEYWORDS`, `YOUTUBE_SEARCH_QUERIES`, ...). That made
the trend feed describe whatever niche the operator typed into `.env` once,
not the niche of the companies actually using the app — a company selling
handmade ceramics got trends about "marketing" and "AI".

The niche now comes from `Company.niche_keywords`, which the Company
Analyzer already extracts during onboarding (from the website, from a
typed description, or from connected social accounts — see
`company_analyzer/graph.py`). Those keywords already drive per-company
relevance scoring; this module makes them drive *collection* too, so the
trends being scored are on-topic in the first place.

Resolution is deliberately a union across every `complete` company rather
than per-company runs: `run_collection()` is a single global pass writing
to one `trends` table deduped on `(source, url)`, and per-company relevance
is scored afterwards by `_score_relevance_per_company`. Collecting the
union once and scoring per company preserves that shape — one pass, N
companies — instead of multiplying external API calls by tenant count.

Ordering is most-recently-updated company first, so with the keyword cap in
play an active company's niche is never crowded out by a dormant one.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import select

from app.config import settings
from app.db.models import Company
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


async def resolve_niche_keywords(limit: int | None = None) -> list[str]:
    """Keywords describing the niche of every onboarded company.

    Returns `[]` when no company has been onboarded yet, or when none has
    keywords — a legitimate operational state (same stance as
    `_score_relevance_node`, which leaves relevance NULL rather than
    erroring). Collectors treat an empty list as "nothing to search yet"
    and skip with a warning.
    """
    cap = limit if limit is not None else settings.TREND_NICHE_MAX_KEYWORDS

    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(Company.niche_keywords)
                    .where(Company.status == "complete")
                    .order_by(Company.updated_at.desc())
                )
            )
            .scalars()
            .all()
        )

    keywords = _dedupe_preserving_order(
        keyword.strip() for row in rows if row for keyword in row if keyword and keyword.strip()
    )
    if not keywords:
        logger.warning(
            "No niche keywords available — no company has completed onboarding with "
            "extracted keywords yet; trend collection has nothing to search for."
        )
    return keywords[:cap]


def _dedupe_preserving_order(keywords) -> list[str]:
    """Case-insensitive dedupe that keeps first-seen casing and order.

    Two companies in the same industry will overlap heavily ("social media"
    vs "Social Media"); without this the cap fills up with near-duplicates
    and later companies never get represented.
    """
    seen: set[str] = set()
    unique: list[str] = []
    for keyword in keywords:
        folded = keyword.casefold()
        if folded in seen:
            continue
        seen.add(folded)
        unique.append(keyword)
    return unique


def to_hashtags(keywords: list[str], limit: int | None = None) -> list[str]:
    """Keywords -> bare hashtag names (no leading '#', which is what the
    Instagram Graph API's `ig_hashtag_search` expects).

    Multi-word keywords collapse to one token ("social media" ->
    "socialmedia") because hashtags can't contain spaces or punctuation.
    Separately capped and much shorter than the general keyword cap: Meta
    limits an account to 30 *unique* hashtags per rolling 7 days, and every
    collection run spends from that budget.
    """
    cap = limit if limit is not None else settings.TREND_NICHE_MAX_HASHTAGS
    tags = _dedupe_preserving_order(
        cleaned
        for keyword in keywords
        if (cleaned := re.sub(r"[^0-9a-z]", "", keyword.casefold()))
    )
    return tags[:cap]
