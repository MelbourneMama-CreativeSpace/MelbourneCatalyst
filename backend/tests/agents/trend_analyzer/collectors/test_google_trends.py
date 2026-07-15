"""Tests for the Google Trends collector."""

from __future__ import annotations

import pandas as pd
import pytest

from app.agents.trend_analyzer.collectors import google_trends as google_trends_module
from app.agents.trend_analyzer.collectors.google_trends import GoogleTrendsCollector


class _FakeTrendReq:
    def __init__(self, **kwargs):
        pass

    def trending_searches(self, pn: str):
        return pd.DataFrame(["AI agents", "Marketing automation"])


class _FailingTrendReq:
    def __init__(self, **kwargs):
        pass

    def trending_searches(self, pn: str):
        raise RuntimeError("Google Trends is down")


async def test_collect_returns_ranked_trend_items(monkeypatch):
    monkeypatch.setattr(google_trends_module, "TrendReq", _FakeTrendReq)

    items = await GoogleTrendsCollector(region="united_states").collect()

    assert [item.title for item in items] == ["AI agents", "Marketing automation"]
    assert items[0].score > items[1].score  # higher rank -> higher score
    assert items[0].raw_metadata == {"region": "united_states", "rank": 0}


async def test_collect_propagates_whole_source_failure(monkeypatch):
    monkeypatch.setattr(google_trends_module, "TrendReq", _FailingTrendReq)

    with pytest.raises(RuntimeError):
        await GoogleTrendsCollector().collect()
