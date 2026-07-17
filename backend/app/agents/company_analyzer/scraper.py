"""Website scraping for the Company Analyzer onboarding pipeline.

Uses `httpx.AsyncClient` (already a dependency) to fetch pages and
`trafilatura` to extract the main article content. Trafilatura beats a
raw BeautifulSoup pass here because it's specifically trained to strip
site chrome (nav, footer, cookie banners, ads) and keep the actual page
body — which is what the profile extractor cares about.

Page discovery is deliberately dumb for the MVP: fetch the homepage,
then probe a fixed set of common "about"-style paths. That's enough for
most marketing sites and avoids the complexity of following outbound
links or respecting robots.txt (which we should add later, before this
is pointed at anything at scale).
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura

from app.agents.company_analyzer.schemas import ScrapedPage

logger = logging.getLogger(__name__)

_USER_AGENT = "mmcs-company-analyzer/0.1 (contact: collabs@melbournemama.org)"
_PROBE_PATHS = [
    "/",
    "/about",
    "/about-us",
    "/services",
    "/products",
    "/pricing",
    "/team",
    "/company",
]


def _normalize_base(url: str) -> str:
    """Add https:// if the user pasted a bare domain, strip trailing slashes."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return f"{parsed.scheme}://{parsed.netloc}"


async def discover_and_scrape(base_url: str, *, max_pages: int) -> list[ScrapedPage]:
    """Fetch the homepage + a heuristic set of about/services/products pages.

    Returns only pages that successfully scraped and yielded non-empty
    main content. Per-page failures are logged and dropped rather than
    aborting the whole run — same isolation pattern as the trend collectors.
    """
    base = _normalize_base(base_url)
    candidate_urls = [urljoin(base + "/", path.lstrip("/")) for path in _PROBE_PATHS[:max_pages]]

    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT},
        timeout=10.0,
        follow_redirects=True,
    ) as client:
        results = await asyncio.gather(
            *(_scrape_one(client, url) for url in candidate_urls),
            return_exceptions=True,
        )

    pages: list[ScrapedPage] = []
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Page scrape errored: %s", result)
            continue
        if result is not None:
            pages.append(result)
    return pages


async def _scrape_one(client: httpx.AsyncClient, url: str) -> ScrapedPage | None:
    try:
        response = await client.get(url)
        if response.status_code >= 400:
            return None
        html = response.text
    except Exception:
        logger.exception("HTTP fetch failed for %s", url)
        return None

    # trafilatura is synchronous — hand it to a worker thread so it
    # doesn't block the event loop on parsing large pages.
    extracted = await asyncio.to_thread(_extract_main_content, html)
    if not extracted:
        return None
    content, title = extracted
    return ScrapedPage(url=url, title=title, content=content)


def _extract_main_content(html: str) -> tuple[str, str | None] | None:
    """Return (content, title) or None if trafilatura found nothing usable."""
    content = trafilatura.extract(html, include_comments=False, include_tables=False)
    if not content or not content.strip():
        return None
    metadata = trafilatura.extract_metadata(html)
    title = metadata.title if metadata else None
    return content, title
