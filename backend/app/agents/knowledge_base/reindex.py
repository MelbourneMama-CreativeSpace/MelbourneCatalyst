"""Scheduled Knowledge Base re-indexing.

Periodically re-scrapes every "complete" company's own website and
re-ingests each page through `ingest_raw_document_if_changed`, so the KB
stays current with the company's live site without a manual re-onboarding
trigger — and without re-embedding pages that haven't changed since the
last run. Registered as an APScheduler interval job in `app/main.py`,
alongside the Trend Analyzer's `run_collection` job.

Scoped to website/product-page content only (the same source the
onboarding pipeline covers) — blog feeds, uploads, and manual entries are
user-triggered, one-off actions, not something with a stable "re-run
this on a schedule" identity, since there's no persisted per-company feed
list to iterate over.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from app.agents.company_analyzer.scraper import classify_source_type, discover_and_scrape
from app.agents.knowledge_base.ingestion import ingest_raw_document_if_changed
from app.agents.knowledge_base.schemas import RawDocument
from app.config import settings
from app.db.models import Company
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)


async def reindex_company(company_id: uuid.UUID, url: str) -> dict:
    """Re-scrape one company's site and re-ingest any changed pages.
    Never raises — a scrape failure for one company shouldn't abort a
    scheduled batch covering many. Returns a small result dict, mostly
    useful for logging."""
    try:
        pages = await discover_and_scrape(url, max_pages=settings.COMPANY_ONBOARDING_MAX_PAGES)
    except Exception:
        logger.exception("Scheduled re-index scrape failed for company %s", company_id)
        return {"pages_scraped": 0, "pages_changed": 0, "chunks_persisted": 0}

    pages_changed = 0
    chunks_persisted = 0
    async with async_session_factory() as session:
        for page in pages:
            raw = RawDocument(
                source_type=classify_source_type(page.url),
                source_url=page.url,
                content=page.content,
                raw_metadata={"page_title": page.title} if page.title else {},
            )
            count, skipped = await ingest_raw_document_if_changed(session, company_id, raw)
            if not skipped:
                pages_changed += 1
                chunks_persisted += count
        await session.commit()

    return {
        "pages_scraped": len(pages),
        "pages_changed": pages_changed,
        "chunks_persisted": chunks_persisted,
    }


async def run_scheduled_reindex() -> None:
    """APScheduler entrypoint — re-indexes every company whose onboarding
    has completed. Companies are processed one at a time so a single
    failure doesn't abort the rest of the batch."""
    async with async_session_factory() as session:
        targets = (
            await session.execute(select(Company.id, Company.url).where(Company.status == "complete"))
        ).all()

    for company_id, url in targets:
        try:
            result = await reindex_company(company_id, url)
            logger.info("Scheduled re-index for company %s: %s", company_id, result)
        except Exception:
            logger.exception("Scheduled re-index failed for company %s", company_id)
