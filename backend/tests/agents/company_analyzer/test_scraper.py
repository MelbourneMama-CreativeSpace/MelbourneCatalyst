"""Tests for the Company Analyzer website scraper."""

from __future__ import annotations

import httpx
import respx

from app.agents.company_analyzer.scraper import _normalize_base, discover_and_scrape

_SAMPLE_HTML = """
<html>
  <head><title>Example Company</title></head>
  <body>
    <nav>Home About Contact</nav>
    <main>
      <article>
        <h1>Welcome to Example Company</h1>
        <p>We build the best widgets in the world. Our team of experts delivers quality.</p>
        <p>Founded in 2020, we serve customers across Europe and North America.</p>
      </article>
    </main>
    <footer>Copyright 2026</footer>
  </body>
</html>
"""


def test_normalize_base_adds_scheme_and_strips_path():
    assert _normalize_base("example.com") == "https://example.com"
    assert _normalize_base("https://example.com/foo/bar") == "https://example.com"
    assert _normalize_base("http://example.com") == "http://example.com"


@respx.mock
async def test_discover_and_scrape_extracts_content_from_reachable_pages():
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text=_SAMPLE_HTML))
    respx.get("https://example.com/about").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/about-us").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/services").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/products").mock(return_value=httpx.Response(404))

    pages = await discover_and_scrape("https://example.com", max_pages=5)

    assert len(pages) == 1
    page = pages[0]
    assert page.url == "https://example.com/"
    assert "widgets" in page.content
    # trafilatura's metadata extractor prefers the article H1 over the
    # <title> tag — either one is a valid page title in practice.
    assert page.title in ("Example Company", "Welcome to Example Company")


@respx.mock
async def test_discover_and_scrape_isolates_per_page_failures():
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text=_SAMPLE_HTML))
    respx.get("https://example.com/about").mock(side_effect=httpx.ConnectError("boom"))
    respx.get("https://example.com/about-us").mock(return_value=httpx.Response(500))
    respx.get("https://example.com/services").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/products").mock(return_value=httpx.Response(404))

    pages = await discover_and_scrape("https://example.com", max_pages=5)

    assert len(pages) == 1  # Only "/" succeeded; the failures didn't kill the batch.


@respx.mock
async def test_discover_and_scrape_returns_empty_when_no_page_yields_content():
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text="<html></html>"))
    for path in ["/about", "/about-us", "/services", "/products"]:
        respx.get(f"https://example.com{path}").mock(return_value=httpx.Response(404))

    pages = await discover_and_scrape("https://example.com", max_pages=5)

    assert pages == []
