"""LangGraph onboarding pipeline for the Company Analyzer.

    START → scrape_pages → gather_owned_context → chunk_and_embed → persist_documents → extract_profile → persist_profile → END

A company's niche can come from three places, and `gather_owned_context` is
what makes them interchangeable: the website (scraped), a description the
operator typed, and the social accounts they've connected. `scrape_pages`
is a no-op when there's no URL, so a business without a website still
reaches extraction with real content behind it.

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
from app.agents.company_analyzer.scraper import classify_source_type, discover_and_scrape
from app.agents.knowledge_base.chunker import chunk_text
from app.agents.knowledge_base.embeddings import embed_documents
from app.agents.knowledge_base.schemas import EmbeddedChunk
from app.config import settings
from app.db.models import Company, Document, PlatformConnection
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

# Statuses that, once set by an earlier node, must not be overwritten by
# `_persist_profile_node`'s default "extraction succeeded -> complete" path.
_TERMINAL_STATUSES = {"failed", "complete_no_profile"}


# Synthetic source URLs for the two non-web inputs. `Document.source_url`
# is NOT NULL and these rows are real Documents (searchable in the
# knowledge base like any scraped page), so they need a stable, obviously
# non-http identifier rather than an empty string.
_DESCRIPTION_SOURCE_URL = "internal:description"
_SOCIAL_SOURCE_URL = "internal:connected-social-accounts"


class CompanyGraphState(TypedDict):
    company_id: uuid.UUID
    url: str | None
    description: str | None
    pages: list[ScrapedPage]
    embedded_chunks: list[EmbeddedChunk]
    profile: CompanyProfile
    status: str
    status_error: str | None


async def _scrape_pages_node(state: CompanyGraphState) -> dict:
    """Scrape the website, if there is one.

    A company onboarding from a typed description or its connected social
    accounts has no URL — that's a normal path, not a failure, so this
    returns no pages and lets `gather_owned_context` supply the content.
    """
    if not state["url"]:
        return {"pages": [], "status": "extracting"}
    pages = await discover_and_scrape(
        state["url"], max_pages=settings.COMPANY_ONBOARDING_MAX_PAGES
    )
    return {"pages": pages, "status": "scraping"}


async def _connected_social_summary(company_id: uuid.UUID) -> str | None:
    """What the company's connected social accounts say about its niche.

    Only the account identities are used. This app stores no post content
    and `metrics.py` deliberately refuses to guess at unverified platform
    response shapes, so inventing a bio/post fetcher here would produce
    code that looks done and breaks on the first real connection. Account
    names are thin but true, and they arrive without a network call.
    """
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(PlatformConnection.platform, PlatformConnection.external_account_name)
                .where(
                    PlatformConnection.company_id == company_id,
                    PlatformConnection.status == "connected",
                )
                .order_by(PlatformConnection.platform.asc())
            )
        ).all()

    lines = [
        f"- {platform}: {name}" if name else f"- {platform}"
        for platform, name in rows
    ]
    if not lines:
        return None
    return "This business operates the following social media accounts:\n" + "\n".join(lines)


async def _gather_owned_context_node(state: CompanyGraphState) -> dict:
    """Fold the operator's description and connected social accounts into
    `pages`, so extraction, chunking and embedding stay one code path
    regardless of which niche signal a company actually has."""
    extra: list[ScrapedPage] = []

    description = (state.get("description") or "").strip()
    if description:
        extra.append(
            ScrapedPage(
                url=_DESCRIPTION_SOURCE_URL,
                title="Business description (provided by the operator)",
                content=description,
                source_type="description",
            )
        )

    social = await _connected_social_summary(state["company_id"])
    if social:
        extra.append(
            ScrapedPage(
                url=_SOCIAL_SOURCE_URL,
                title="Connected social accounts",
                content=social,
                source_type="social_profile",
            )
        )

    if not extra:
        return {}
    return {"pages": state["pages"] + extra}


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
                    source_type=page.source_type or classify_source_type(page.url),
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
        # No content from any source — mark failed rather than sending
        # empty input to the LLM and pretending we succeeded. Reachable
        # only when a URL was given and scraping yielded nothing: the API
        # layer rejects a request with neither URL nor description.
        return {
            "profile": CompanyProfile(),
            "status": "failed",
            "status_error": (
                "No content could be gathered — the provided URL yielded no pages, "
                "and no description or connected social account was available."
            ),
        }
    aggregated = "\n\n---\n\n".join(
        f"# {page.title or page.url}\n{page.content}" for page in state["pages"]
    )
    profile, extracted_ok = await extract_company_profile(aggregated)
    if not extracted_ok:
        # Scraping worked, but no profile came out of it (missing
        # ANTHROPIC_API_KEY, or the Claude call failed) — distinct from
        # "complete", so the UI doesn't show a silently blank profile as a
        # success.
        return {
            "profile": profile,
            "status": "complete_no_profile",
            "status_error": (
                "Content was gathered successfully, but no profile could be "
                "generated (check ANTHROPIC_API_KEY / Claude API availability)."
            ),
        }
    return {"profile": profile, "status": "extracting"}


async def _persist_profile_node(state: CompanyGraphState) -> dict:
    profile = state["profile"]
    # Earlier nodes may have already set a terminal status (failed,
    # complete_no_profile) — preserve it rather than overwriting with the
    # extraction-succeeded default.
    incoming_status = state.get("status")
    final_status = incoming_status if incoming_status in _TERMINAL_STATUSES else "complete"
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
        company.products_and_services = profile.products_and_services or None
        company.status = final_status
        company.status_error = status_error
        company.updated_at = datetime.now(timezone.utc)

        await session.commit()

    return {"status": final_status}


def _build_graph():
    graph = StateGraph(CompanyGraphState)
    graph.add_node("scrape_pages", _scrape_pages_node)
    graph.add_node("gather_owned_context", _gather_owned_context_node)
    graph.add_node("chunk_and_embed", _chunk_and_embed_node)
    graph.add_node("persist_documents", _persist_documents_node)
    graph.add_node("extract_profile", _extract_profile_node)
    graph.add_node("persist_profile", _persist_profile_node)

    graph.add_edge(START, "scrape_pages")
    graph.add_edge("scrape_pages", "gather_owned_context")
    graph.add_edge("gather_owned_context", "chunk_and_embed")
    graph.add_edge("chunk_and_embed", "persist_documents")
    graph.add_edge("persist_documents", "extract_profile")
    graph.add_edge("extract_profile", "persist_profile")
    graph.add_edge("persist_profile", END)

    return graph.compile()


_onboarding_graph = _build_graph()


async def run_onboarding(
    company_id: uuid.UUID, url: str | None, description: str | None = None
) -> None:
    """Run the onboarding pipeline for one Company. Called via FastAPI's
    BackgroundTasks after `POST /companies` has created the pending row.
    Failures are captured onto the Company row rather than raised — the
    caller is fire-and-forget.

    At least one of `url` / `description` should be set (the API layer
    enforces it); a company with neither and no connected social account
    ends at status `failed` with nothing to extract from.
    """
    initial_state: CompanyGraphState = {
        "company_id": company_id,
        "url": url,
        "description": description,
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
