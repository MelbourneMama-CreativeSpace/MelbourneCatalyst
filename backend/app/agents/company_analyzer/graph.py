"""LangGraph onboarding pipeline for the Company Analyzer.

    START → scrape_pages → chunk_and_embed → persist_documents → extract_profile → persist_profile → END

One-shot pipeline (unlike the Trend Analyzer's recurring schedule). Kicked
off by `POST /api/v1/companies` via FastAPI's `BackgroundTasks` — no
Celery/Redis needed for the MVP, since onboarding is user-triggered and
short (~30s end-to-end).

Consistent shape with `trend_analyzer/graph.py` so the codebase reads as
one system: TypedDict state, each node returns a partial dict, one
compiled graph exposed via `run_onboarding()`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from app.agents.company_analyzer.extractor import extract_company_profile
from app.agents.company_analyzer.schemas import CompanyProfile, ScrapedPage
from app.agents.company_analyzer.scraper import discover_and_scrape
from app.agents.knowledge_base.chunker import chunk_text
from app.agents.knowledge_base.embeddings import embed_documents
from app.agents.knowledge_base.schemas import EmbeddedChunk
from app.config import settings
from app.db.models import Company, Document
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


class CompanyGraphState(TypedDict):
    company_id: uuid.UUID
    url: str
    pages: list[ScrapedPage]
    embedded_chunks: list[EmbeddedChunk]
    profile: CompanyProfile
    status: str
    status_error: str | None


async def _scrape_pages_node(state: CompanyGraphState) -> dict:
    pages = await discover_and_scrape(
        state["url"], max_pages=settings.COMPANY_ONBOARDING_MAX_PAGES
    )
    return {"pages": pages, "status": "scraping"}


async def _chunk_and_embed_node(state: CompanyGraphState) -> dict:
    embedded: list[EmbeddedChunk] = []
    all_chunks_by_page: list[tuple[ScrapedPage, list[str]]] = []
    flat_chunks: list[str] = []

    for page in state["pages"]:
        chunks = chunk_text(page.content)
        if chunks:
            all_chunks_by_page.append((page, chunks))
            flat_chunks.extend(chunks)

    embeddings = await embed_documents(flat_chunks)

    cursor = 0
    for page, chunks in all_chunks_by_page:
        for i, chunk in enumerate(chunks):
            embedded.append(
                EmbeddedChunk(
                    source_type="website",
                    source_url=page.url,
                    chunk_index=i,
                    content=chunk,
                    embedding=embeddings[cursor],
                    raw_metadata={"page_title": page.title} if page.title else {},
                )
            )
            cursor += 1

    return {"embedded_chunks": embedded}


async def _persist_documents_node(state: CompanyGraphState) -> dict:
    if not state["embedded_chunks"]:
        return {}
    async with async_session_factory() as session:
        session.add_all(
            [
                Document(
                    id=uuid.uuid4(),
                    company_id=state["company_id"],
                    source_type=chunk.source_type,
                    source_url=chunk.source_url,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    embedding=chunk.embedding,
                    raw_metadata=chunk.raw_metadata,
                )
                for chunk in state["embedded_chunks"]
            ]
        )
        await session.commit()
    return {}


async def _extract_profile_node(state: CompanyGraphState) -> dict:
    if not state["pages"]:
        # No content scraped at all — mark failed rather than sending
        # empty input to the LLM and pretending we succeeded.
        return {
            "profile": CompanyProfile(),
            "status": "failed",
            "status_error": "No pages could be scraped from the provided URL",
        }
    aggregated = "\n\n---\n\n".join(
        f"# {page.title or page.url}\n{page.content}" for page in state["pages"]
    )
    profile = await extract_company_profile(aggregated)
    return {"profile": profile, "status": "extracting"}


async def _persist_profile_node(state: CompanyGraphState) -> dict:
    profile = state["profile"]
    # If _extract_profile_node already set failed, keep that terminal state.
    final_status = "failed" if state.get("status") == "failed" else "complete"
    status_error = state.get("status_error")

    async with async_session_factory() as session:
        company = await session.get(Company, state["company_id"])
        if company is None:
            logger.error("Company %s vanished mid-onboarding", state["company_id"])
            return {"status": "failed", "status_error": "company row not found"}

        # Only apply extracted fields when we actually have them —
        # avoid clobbering an operator-edited row later.
        if profile.name is not None:
            company.name = profile.name
        company.industry = profile.industry
        company.business_model = profile.business_model
        company.target_audience = profile.target_audience
        company.brand_voice = profile.brand_voice
        company.unique_value_prop = profile.unique_value_prop
        company.niche_keywords = profile.niche_keywords or None
        company.summary = profile.summary
        company.status = final_status
        company.status_error = status_error
        company.updated_at = datetime.now(timezone.utc)

        await session.commit()

    return {"status": final_status}


def _build_graph():
    graph = StateGraph(CompanyGraphState)
    graph.add_node("scrape_pages", _scrape_pages_node)
    graph.add_node("chunk_and_embed", _chunk_and_embed_node)
    graph.add_node("persist_documents", _persist_documents_node)
    graph.add_node("extract_profile", _extract_profile_node)
    graph.add_node("persist_profile", _persist_profile_node)

    graph.add_edge(START, "scrape_pages")
    graph.add_edge("scrape_pages", "chunk_and_embed")
    graph.add_edge("chunk_and_embed", "persist_documents")
    graph.add_edge("persist_documents", "extract_profile")
    graph.add_edge("extract_profile", "persist_profile")
    graph.add_edge("persist_profile", END)

    return graph.compile()


_onboarding_graph = _build_graph()


async def run_onboarding(company_id: uuid.UUID, url: str) -> None:
    """Run the onboarding pipeline for one Company. Called via FastAPI's
    BackgroundTasks after `POST /companies` has created the pending row.
    Failures are captured onto the Company row rather than raised — the
    caller is fire-and-forget."""
    initial_state: CompanyGraphState = {
        "company_id": company_id,
        "url": url,
        "pages": [],
        "embedded_chunks": [],
        "profile": CompanyProfile(),
        "status": "pending",
        "status_error": None,
    }
    try:
        await _onboarding_graph.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("Onboarding graph crashed for company %s", company_id)
        # Best-effort: mark the row as failed so the UI stops polling.
        try:
            async with async_session_factory() as session:
                company = await session.get(Company, company_id)
                if company is not None:
                    company.status = "failed"
                    company.status_error = str(exc)[:512]
                    await session.commit()
        except Exception:
            logger.exception("Failed to mark company %s as failed", company_id)
