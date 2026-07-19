"""Tests for the RSS-driven blog/article Knowledge Base indexer."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.agents.knowledge_base import blog_indexer

_ARTICLE_HTML = """
<html>
  <head><title>How We Grew Our Community</title></head>
  <body>
    <article>
      <h1>How We Grew Our Community</h1>
      <p>We started with a handful of members and now run weekly workshops for parents.</p>
      <p>Our approach focuses on low-pressure, creative activities that fit into a busy week.</p>
    </article>
  </body>
</html>
"""


@pytest.fixture(autouse=True)
def _skip_real_ssrf_dns_lookup(monkeypatch):
    monkeypatch.setattr(blog_indexer, "validate_public_url", lambda url: None)


async def test_index_blog_feeds_returns_empty_for_no_feeds():
    result = await blog_indexer.index_blog_feeds([], max_articles=5)
    assert result == []


async def test_index_blog_feeds_returns_empty_when_max_articles_is_zero(monkeypatch):
    monkeypatch.setattr(blog_indexer, "_entry_links", lambda feed_url, limit: ["https://example.com/post"])
    result = await blog_indexer.index_blog_feeds(["https://example.com/feed"], max_articles=0)
    assert result == []


@respx.mock
async def test_index_blog_feeds_produces_raw_documents_from_articles(monkeypatch):
    monkeypatch.setattr(
        blog_indexer, "_entry_links", lambda feed_url, limit: ["https://example.com/post-1"]
    )
    respx.get("https://example.com/post-1").mock(return_value=httpx.Response(200, text=_ARTICLE_HTML))

    documents = await blog_indexer.index_blog_feeds(["https://example.com/feed"], max_articles=5)

    assert len(documents) == 1
    doc = documents[0]
    assert doc.source_type == "blog"
    assert doc.source_url == "https://example.com/post-1"
    assert "workshops for parents" in doc.content
    assert doc.raw_metadata.get("title") == "How We Grew Our Community"


@respx.mock
async def test_index_blog_feeds_skips_failed_articles_without_aborting(monkeypatch):
    monkeypatch.setattr(
        blog_indexer,
        "_entry_links",
        lambda feed_url, limit: ["https://example.com/broken", "https://example.com/post-1"],
    )
    respx.get("https://example.com/broken").mock(return_value=httpx.Response(500))
    respx.get("https://example.com/post-1").mock(return_value=httpx.Response(200, text=_ARTICLE_HTML))

    documents = await blog_indexer.index_blog_feeds(["https://example.com/feed"], max_articles=5)

    assert len(documents) == 1
    assert documents[0].source_url == "https://example.com/post-1"


@respx.mock
async def test_index_blog_feeds_respects_max_articles_cap(monkeypatch):
    monkeypatch.setattr(
        blog_indexer,
        "_entry_links",
        lambda feed_url, limit: [f"https://example.com/post-{i}" for i in range(limit)],
    )
    for i in range(10):
        respx.get(f"https://example.com/post-{i}").mock(
            return_value=httpx.Response(200, text=_ARTICLE_HTML)
        )

    documents = await blog_indexer.index_blog_feeds(["https://example.com/feed"], max_articles=3)

    assert len(documents) <= 3


async def test_index_blog_feeds_rejects_unsafe_feed_url(monkeypatch):
    # feedparser.parse() fetches the feed URL itself — the autouse fixture
    # above no-ops validate_public_url for every other test in this file,
    # so restore the real check here to prove the feed URL (not just each
    # article URL) actually gets SSRF-validated before feedparser touches it.
    from app.security import validate_public_url as real_validate_public_url

    monkeypatch.setattr(blog_indexer, "validate_public_url", real_validate_public_url)
    parse_calls = []
    monkeypatch.setattr(
        blog_indexer.feedparser, "parse", lambda url: parse_calls.append(url) or None
    )

    result = await blog_indexer.index_blog_feeds(["http://192.168.1.1/rss"], max_articles=5)

    assert result == []
    assert parse_calls == []  # feedparser.parse must never have been called


async def test_index_blog_feeds_returns_empty_when_feed_parsing_raises(monkeypatch):
    def _boom(feed_url, limit):
        raise RuntimeError("feed unreachable")

    monkeypatch.setattr(blog_indexer, "_entry_links", _boom)

    result = await blog_indexer.index_blog_feeds(["https://example.com/feed"], max_articles=5)

    assert result == []
