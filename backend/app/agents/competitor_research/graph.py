"""LangGraph onboarding pipeline for a Competitor.

    START → scrape_pages → extract_profile → persist_profile → END

Same shape as `company_analyzer/graph.py`'s onboarding pipeline, and
reuses its scraper/extractor directly rather than duplicating them — a
competitor's own website is scraped and profiled exactly the way the
target company's is. The one structural difference: no
chunk_and_embed/persist_documents step, since a competitor's scraped
content isn't part of the target company's own searchable Knowledge
Base — it's transient input to the comparison generated separately by
`comparison_graph.py`.

One-shot, kicked off by `POST /competitor-research/competitors` via
FastAPI's `BackgroundTasks` — same reasoning as company onboarding:
scraping takes real wall-clock time (~10-30s), so this isn't a good fit
for Content Management's synchronous-POST pattern.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.company_analyzer.extractor import extract_company_profile
from app.agents.company_analyzer.schemas import CompanyProfile, ScrapedPage
from app.agents.company_analyzer.scraper import discover_and_scrape
from app.config import settings
from app.db.models import Competitor
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

# Statuses that, once set by an earlier node, must not be overwritten by
# `_persist_profile_node`'s default "extraction succeeded -> complete" path.
_TERMINAL_STATUSES = {"failed", "complete_no_profile"}


class CompetitorGraphState(TypedDict):
    competitor_id: uuid.UUID
    url: str
    pages: list[ScrapedPage]
    profile: CompanyProfile
    status: str
    status_error: str | None


async def _scrape_pages_node(state: CompetitorGraphState) -> dict:
    pages = await discover_and_scrape(
        state["url"], max_pages=settings.COMPANY_ONBOARDING_MAX_PAGES
    )
    return {"pages": pages, "status": "scraping"}


async def _extract_profile_node(state: CompetitorGraphState) -> dict:
    if not state["pages"]:
        return {
            "profile": CompanyProfile(),
            "status": "failed",
            "status_error": "No pages could be scraped from the provided URL",
        }
    aggregated = "\n\n---\n\n".join(
        f"# {page.title or page.url}\n{page.content}" for page in state["pages"]
    )
    profile, extracted_ok = await extract_company_profile(aggregated)
    if not extracted_ok:
        return {
            "profile": profile,
            "status": "complete_no_profile",
            "status_error": (
                "Website was scraped successfully, but no profile could be "
                "generated (check ANTHROPIC_API_KEY / Claude API availability)."
            ),
        }
    return {"profile": profile, "status": "extracting"}


async def _persist_profile_node(state: CompetitorGraphState) -> dict:
    profile = state["profile"]
    incoming_status = state.get("status")
    final_status = incoming_status if incoming_status in _TERMINAL_STATUSES else "complete"
    status_error = state.get("status_error")

    async with async_session_factory() as session:
        competitor = await session.get(Competitor, state["competitor_id"])
        if competitor is None:
            logger.error("Competitor %s vanished mid-onboarding", state["competitor_id"])
            return {"status": "failed", "status_error": "competitor row not found"}

        if profile.name is not None:
            competitor.name = profile.name
        competitor.industry = profile.industry
        competitor.business_model = profile.business_model
        competitor.target_audience = profile.target_audience
        competitor.brand_voice = profile.brand_voice
        competitor.unique_value_prop = profile.unique_value_prop
        competitor.summary = profile.summary
        competitor.status = final_status
        competitor.status_error = status_error
        competitor.updated_at = datetime.now(timezone.utc)

        await session.commit()

    return {"status": final_status}


def _build_graph():
    graph = StateGraph(CompetitorGraphState)
    graph.add_node("scrape_pages", _scrape_pages_node)
    graph.add_node("extract_profile", _extract_profile_node)
    graph.add_node("persist_profile", _persist_profile_node)

    graph.add_edge(START, "scrape_pages")
    graph.add_edge("scrape_pages", "extract_profile")
    graph.add_edge("extract_profile", "persist_profile")
    graph.add_edge("persist_profile", END)

    return graph.compile()


_competitor_graph = _build_graph()


async def run_competitor_onboarding(competitor_id: uuid.UUID, url: str) -> None:
    """Run the onboarding pipeline for one Competitor. Called via FastAPI's
    BackgroundTasks after `POST /competitor-research/competitors` has
    created the pending row. Failures are captured onto the row rather than
    raised — the caller is fire-and-forget."""
    initial_state: CompetitorGraphState = {
        "competitor_id": competitor_id,
        "url": url,
        "pages": [],
        "profile": CompanyProfile(),
        "status": "pending",
        "status_error": None,
    }
    try:
        await _competitor_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("Competitor onboarding graph crashed for competitor %s", competitor_id)
        try:
            async with async_session_factory() as session:
                competitor = await session.get(Competitor, competitor_id)
                if competitor is not None:
                    competitor.status = "failed"
                    competitor.status_error = str(exc)[:512]
                    await session.commit()
        except Exception:
            logger.exception("Failed to mark competitor %s as failed", competitor_id)
