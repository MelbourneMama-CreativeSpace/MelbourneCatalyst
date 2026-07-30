"""Tests for the Company Analyzer website scraper."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.agents.company_analyzer import scraper
from app.agents.company_analyzer.scraper import classify_source_type, normalize_url, discover_and_scrape
from app.security import UnsafeUrlError

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


@pytest.fixture(autouse=True)
def _skip_real_ssrf_dns_lookup(monkeypatch):
    """These tests exercise scraping/extraction logic, not SSRF blocking
    (that's covered by test_security.py and the dedicated tests below) —
    no-op the check so tests don't depend on real DNS resolution."""
    monkeypatch.setattr(scraper, "validate_public_url", lambda url: None)


def test_normalize_url_adds_scheme_and_strips_path():
    assert normalize_url("example.com") == "https://example.com"
    assert normalize_url("https://example.com/foo/bar") == "https://example.com"
    assert normalize_url("http://example.com") == "http://example.com"


def test_classify_source_type_tags_product_and_pricing_paths():
    assert classify_source_type("https://example.com/products") == "product_page"
    assert classify_source_type("https://example.com/pricing") == "product_page"
    assert classify_source_type("https://example.com/shop/widget") == "product_page"
    assert classify_source_type("https://example.com/store") == "product_page"


def test_classify_source_type_tags_other_paths_as_website():
    assert classify_source_type("https://example.com/about") == "website"
    assert classify_source_type("https://example.com/") == "website"
    assert classify_source_type("https://example.com/team") == "website"


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


# --- SSRF protection ---------------------------------------------------


async def test_discover_and_scrape_refuses_an_unsafe_base_url(monkeypatch):
    def fake_validate(url: str) -> None:
        raise UnsafeUrlError("blocked for test")

    monkeypatch.setattr(scraper, "validate_public_url", fake_validate)

    pages = await discover_and_scrape("https://internal.example.com", max_pages=5)

    assert pages == []


@respx.mock
async def test_discover_and_scrape_blocks_a_redirect_to_an_unsafe_target(monkeypatch):
    def fake_validate(url: str) -> None:
        # Base URL is fine; only the redirect target is "unsafe" here —
        # proves the event hook checks every hop, not just the first request.
        if "169.254.169.254" in url:
            raise UnsafeUrlError("blocked for test")

    monkeypatch.setattr(scraper, "validate_public_url", fake_validate)

    respx.get("https://example.com/").mock(
        return_value=httpx.Response(
            302, headers={"Location": "http://169.254.169.254/secret"}
        )
    )
    for path in ["/about", "/about-us", "/services", "/products"]:
        respx.get(f"https://example.com{path}").mock(return_value=httpx.Response(404))

    pages = await discover_and_scrape("https://example.com", max_pages=5)

    assert pages == []  # redirect target was blocked; nothing else yielded content
