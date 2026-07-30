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

`POST /companies` is unauthenticated and hands this module a
user-supplied URL — every request (including redirects, since
`follow_redirects=True`) is validated via an httpx event hook so this
can't be used to probe internal/cloud-metadata addresses (SSRF). See
`app/security.py`.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura

from app.agents.company_analyzer.schemas import ScrapedPage
from app.security import UnsafeUrlError, validate_public_url

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

# Path fragments that mark a scraped page as product/pricing content
# rather than generic "website" content — lets KB search/audit tools
# filter product pages out from general site copy. Public (not
# `_`-prefixed) so both the onboarding graph and the scheduled KB
# re-index job classify pages identically.
_PRODUCT_PAGE_PATH_MARKERS = ("product", "pricing", "shop", "store")


def classify_source_type(url: str) -> str:
    path = urlparse(url).path.lower()
    if any(marker in path for marker in _PRODUCT_PAGE_PATH_MARKERS):
        return "product_page"
    return "website"


def normalize_url(url: str) -> str:
    """Add https:// if the user pasted a bare domain, strip to scheme+host.

    Public (not `_`-prefixed) because the API layer uses this too, to keep
    `example.com` / `https://example.com` / `https://example.com/` — which
    Pydantic's `HttpUrl` doesn't itself normalize consistently — resolving
    to the same Company row instead of three duplicate ones.
    """
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return f"{parsed.scheme}://{parsed.netloc}"


async def _reject_unsafe_requests(request: httpx.Request) -> None:
    """httpx event hook: validated for every request sent through the
    client, including each hop of a redirect chain — a malicious server
    can't bypass the check by 302'ing to an internal address."""
    await asyncio.to_thread(validate_public_url, str(request.url))


async def discover_and_scrape(base_url: str, *, max_pages: int) -> list[ScrapedPage]:
    """Fetch the homepage + a heuristic set of about/services/products pages.

    Returns only pages that successfully scraped and yielded non-empty
    main content. Per-page failures are logged and dropped rather than
    aborting the whole run — same isolation pattern as the trend collectors.
    """
    base = normalize_url(base_url)
    try:
        await asyncio.to_thread(validate_public_url, base)
    except UnsafeUrlError:
        logger.warning("Refusing to scrape unsafe URL: %s", base)
        return []

    candidate_urls = [urljoin(base + "/", path.lstrip("/")) for path in _PROBE_PATHS[:max_pages]]

    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT},
        timeout=10.0,
        follow_redirects=True,
        event_hooks={"request": [_reject_unsafe_requests]},
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
