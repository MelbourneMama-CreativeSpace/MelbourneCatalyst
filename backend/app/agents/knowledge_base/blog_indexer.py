"""Blog/article Knowledge Base source — RSS-driven, per-request feed list
(distinct from the Trend Analyzer's global `RSS_FEED_URLS`, since a
company's own blog feeds are company-specific, not a shared trend source).

`feedparser` gives us entry links; each entry's article page is then
scraped and its main content extracted the same way the Company Analyzer
scrapes the company's own site (httpx + trafilatura, SSRF-guarded) — an
RSS summary alone is usually too thin to be useful for retrieval.
"""

from __future__ import annotations

import asyncio
import logging

import feedparser
import httpx
import trafilatura

from app.agents.knowledge_base.schemas import RawDocument
from app.security import UnsafeUrlError, validate_public_url

logger = logging.getLogger(__name__)

_USER_AGENT = "mmcs-knowledge-base/0.1 (contact: collabs@melbournemama.org)"


async def _reject_unsafe_requests(request: httpx.Request) -> None:
    await asyncio.to_thread(validate_public_url, str(request.url))


def _entry_links(feed_url: str, limit: int) -> list[str]:
    # feedparser fetches `feed_url` itself (it accepts a plain URL string,
    # not just pre-fetched bytes) — validate it the same way every other
    # user-supplied URL in this codebase is validated before any network
    # library touches it, since `feed_urls` here comes straight from the
    # request body.
    validate_public_url(feed_url)
    parsed = feedparser.parse(feed_url)
    links = []
    for entry in parsed.entries[:limit]:
        link = entry.get("link")
        if link:
            links.append(link)
    return links


async def _fetch_article(client: httpx.AsyncClient, url: str) -> RawDocument | None:
    try:
        await asyncio.to_thread(validate_public_url, url)
    except UnsafeUrlError:
        logger.warning("Refusing to fetch unsafe article URL: %s", url)
        return None
    try:
        response = await client.get(url)
        if response.status_code >= 400:
            return None
        html = response.text
    except Exception:
        logger.exception("HTTP fetch failed for article %s", url)
        return None

    content = await asyncio.to_thread(
        trafilatura.extract, html, include_comments=False, include_tables=False
    )
    if not content or not content.strip():
        return None
    metadata = await asyncio.to_thread(trafilatura.extract_metadata, html)
    title = metadata.title if metadata else None

    return RawDocument(
        source_type="blog",
        source_url=url,
        content=content,
        raw_metadata={"title": title} if title else {},
    )


async def index_blog_feeds(feed_urls: list[str], *, max_articles: int) -> list[RawDocument]:
    """Fetch up to `max_articles` articles total (spread evenly across
    `feed_urls` in the order given) and return one `RawDocument` per
    successfully-scraped article. Per-feed and per-article failures are
    logged and skipped rather than aborting the whole run — same isolation
    pattern as the website scraper and trend collectors. Never raises."""
    if not feed_urls or max_articles <= 0:
        return []

    per_feed_limit = max(1, -(-max_articles // len(feed_urls)))  # ceil division
    article_urls: list[str] = []
    for feed_url in feed_urls:
        try:
            article_urls.extend(await asyncio.to_thread(_entry_links, feed_url, per_feed_limit))
        except Exception:
            logger.exception("RSS parse failed for %s", feed_url)
    article_urls = article_urls[:max_articles]

    if not article_urls:
        return []

    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT},
        timeout=10.0,
        follow_redirects=True,
        event_hooks={"request": [_reject_unsafe_requests]},
    ) as client:
        results = await asyncio.gather(
            *(_fetch_article(client, url) for url in article_urls), return_exceptions=True
        )

    documents: list[RawDocument] = []
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Article fetch errored: %s", result)
            continue
        if result is not None:
            documents.append(result)
    return documents
