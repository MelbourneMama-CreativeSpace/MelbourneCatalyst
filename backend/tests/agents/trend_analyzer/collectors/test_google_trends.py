"""Tests for the Google Trends collector."""

from __future__ import annotations

import pandas as pd

from app.agents.trend_analyzer.collectors import google_trends as google_trends_module
from app.agents.trend_analyzer.collectors.google_trends import (
    GoogleTrendsCollector,
    _parse_growth_value,
)


class _FakeTrendReq:
    def __init__(self, **kwargs):
        self._keyword = None

    def build_payload(self, kw_list, timeframe=None, geo=None):
        self._keyword = kw_list[0]

    def related_queries(self):
        return {
            self._keyword: {
                "rising": pd.DataFrame(
                    {
                        "query": ["ai marketing tools", "social media trends"],
                        "value": [3800, 150],
                    }
                )
            }
        }


class _EmptyRisingTrendReq:
    def __init__(self, **kwargs):
        self._keyword = None

    def build_payload(self, kw_list, timeframe=None, geo=None):
        self._keyword = kw_list[0]

    def related_queries(self):
        return {self._keyword: {"rising": pd.DataFrame(columns=["query", "value"])}}


class _PartiallyFailingTrendReq(_FakeTrendReq):
    def build_payload(self, kw_list, timeframe=None, geo=None):
        if kw_list[0] == "bad keyword":
            raise RuntimeError("Google Trends is down")
        super().build_payload(kw_list, timeframe=timeframe, geo=geo)


def _stub_resolve(keywords: list[str]):
    async def _resolve(limit=None):
        return keywords

    return _resolve


def test_parse_growth_value_handles_numbers_and_breakout():
    assert _parse_growth_value(150) == 150.0
    assert _parse_growth_value("150") == 150.0
    assert _parse_growth_value("Breakout") == 5000.0
    assert _parse_growth_value("breakout") == 5000.0
    assert _parse_growth_value(None) == 0.0
    assert _parse_growth_value("not a number") == 0.0


async def test_collect_returns_rising_related_queries(monkeypatch):
    monkeypatch.setattr(google_trends_module, "TrendReq", _FakeTrendReq)

    items = await GoogleTrendsCollector(region="US", seed_keywords=["marketing"]).collect()

    assert [item.title for item in items] == ["ai marketing tools", "social media trends"]
    assert items[0].score == 3800.0
    assert items[0].raw_metadata == {"seed_keyword": "marketing", "growth": 3800}
    assert items[0].url == "https://trends.google.com/trends/explore?q=ai+marketing+tools"


async def test_collect_returns_empty_when_no_rising_queries(monkeypatch):
    monkeypatch.setattr(google_trends_module, "TrendReq", _EmptyRisingTrendReq)

    items = await GoogleTrendsCollector(seed_keywords=["marketing"]).collect()

    assert items == []


async def test_collect_isolates_a_failing_seed_keyword(monkeypatch):
    monkeypatch.setattr(google_trends_module, "TrendReq", _PartiallyFailingTrendReq)

    items = await GoogleTrendsCollector(seed_keywords=["bad keyword", "marketing"]).collect()

    assert len(items) == 2
    assert all(item.raw_metadata["seed_keyword"] == "marketing" for item in items)


async def test_collect_resolves_the_niche_when_no_keywords_are_passed(monkeypatch):
    """Seeds come from the onboarded companies, not from .env."""
    monkeypatch.setattr(google_trends_module, "TrendReq", _FakeTrendReq)
    monkeypatch.setattr(
        google_trends_module, "resolve_niche_keywords", _stub_resolve(["ceramics"])
    )

    items = await GoogleTrendsCollector().collect()

    assert items
    assert all(item.raw_metadata["seed_keyword"] == "ceramics" for item in items)


async def test_collect_resolves_the_niche_on_every_run(monkeypatch):
    """`graph.py` builds its collectors once at import time, so a niche read
    in __init__ would be frozen at process start and never see a company
    onboarded afterwards."""
    monkeypatch.setattr(google_trends_module, "TrendReq", _FakeTrendReq)
    collector = GoogleTrendsCollector()

    monkeypatch.setattr(google_trends_module, "resolve_niche_keywords", _stub_resolve(["first"]))
    first = await collector.collect()
    monkeypatch.setattr(google_trends_module, "resolve_niche_keywords", _stub_resolve(["second"]))
    second = await collector.collect()

    assert first[0].raw_metadata["seed_keyword"] == "first"
    assert second[0].raw_metadata["seed_keyword"] == "second"


async def test_collect_is_a_no_op_when_no_company_has_a_niche_yet(monkeypatch):
    def _explode(**kwargs):
        raise AssertionError("Google Trends must not be queried without a niche")

    monkeypatch.setattr(google_trends_module, "TrendReq", _explode)
    monkeypatch.setattr(google_trends_module, "resolve_niche_keywords", _stub_resolve([]))

    assert await GoogleTrendsCollector().collect() == []
