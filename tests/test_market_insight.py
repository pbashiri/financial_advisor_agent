"""Tests for market_insight module."""

import pytest

from financial_advisor.market_insight import (
    MarketInsightResult,
    fetch_market_insight,
)


def test_market_insight_result_has_any():
    assert MarketInsightResult().has_any() is False
    assert MarketInsightResult(alpha_vantage_summary="x").has_any() is True
    assert MarketInsightResult(finnhub_summary="y").has_any() is True


def test_market_insight_result_to_briefing_text():
    assert MarketInsightResult().to_briefing_text() == ""

    r = MarketInsightResult(alpha_vantage_summary="News 1")
    assert "Alpha Vantage" in r.to_briefing_text()
    assert "News 1" in r.to_briefing_text()

    r2 = MarketInsightResult(finnhub_summary="Headline 1")
    assert "Finnhub" in r2.to_briefing_text()
    assert "Headline 1" in r2.to_briefing_text()


@pytest.mark.asyncio
async def test_fetch_market_insight_no_keys_returns_empty():
    result = await fetch_market_insight(alpha_vantage_api_key=None, finnhub_api_key=None)
    assert result.alpha_vantage_summary is None
    assert result.finnhub_summary is None
    assert result.has_any() is False
