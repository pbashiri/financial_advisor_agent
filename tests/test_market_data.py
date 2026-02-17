"""Tests for market data module."""

from unittest.mock import patch

import pytest

from financial_advisor.config import DEFAULT_MAJOR_INDICES
from financial_advisor.market_data import (
    QuoteSnapshot,
    format_quote,
    get_index_quotes,
    get_multiple_quotes,
    get_quote,
)

# We don't test actual yfinance API calls (network-dependent).
# Async get_quote/get_multiple_quotes/get_index_quotes are tested with mocked _fetch_quote_sync.


def test_quote_snapshot_creation():
    q = QuoteSnapshot(
        symbol="AAPL",
        name="Apple Inc.",
        price=185.50,
        change=2.30,
        change_percent=1.25,
        day_high=186.00,
        day_low=183.00,
        week_52_high=199.62,
        week_52_low=164.08,
        market_cap=2_870_000_000_000,
    )
    assert q.symbol == "AAPL"
    assert q.price == 185.50
    assert q.error is None


def test_quote_snapshot_with_error():
    q = QuoteSnapshot(
        symbol="INVALID",
        name="INVALID",
        price=None,
        change=None,
        change_percent=None,
        day_high=None,
        day_low=None,
        week_52_high=None,
        week_52_low=None,
        market_cap=None,
        error="Not found",
    )
    assert q.error == "Not found"
    assert q.price is None


def test_format_quote_positive():
    q = QuoteSnapshot(
        symbol="AAPL",
        name="Apple Inc.",
        price=185.50,
        change=2.30,
        change_percent=1.25,
        day_high=186.00,
        day_low=183.00,
        week_52_high=199.62,
        week_52_low=164.08,
        market_cap=None,
    )
    result = format_quote(q)
    assert "Apple Inc." in result
    assert "AAPL" in result
    assert "$185.50" in result
    assert "+2.30" in result
    assert "+1.25%" in result


def test_format_quote_negative():
    q = QuoteSnapshot(
        symbol="XYZ",
        name="XYZ Corp",
        price=50.00,
        change=-3.50,
        change_percent=-6.54,
        day_high=54.00,
        day_low=49.50,
        week_52_high=80.00,
        week_52_low=45.00,
        market_cap=None,
    )
    result = format_quote(q)
    assert "-3.50" in result
    assert "-6.54%" in result


def test_format_quote_unavailable():
    q = QuoteSnapshot(
        symbol="BAD",
        name="BAD",
        price=None,
        change=None,
        change_percent=None,
        day_high=None,
        day_low=None,
        week_52_high=None,
        week_52_low=None,
        market_cap=None,
        error="Failed",
    )
    result = format_quote(q)
    assert "unavailable" in result.lower()


def test_format_quote_no_change_shows_na():
    """When price exists but change is None, display N/A for change."""
    q = QuoteSnapshot(
        symbol="XYZ",
        name="XYZ Corp",
        price=50.00,
        change=None,
        change_percent=None,
        day_high=54.0,
        day_low=49.0,
        week_52_high=80.0,
        week_52_low=45.0,
        market_cap=None,
    )
    result = format_quote(q)
    assert "N/A" in result
    assert "$50.00" in result


def test_major_indices_defined():
    """Default major indices (from config/settings) include expected symbols."""
    assert "^GSPC" in DEFAULT_MAJOR_INDICES
    assert "^IXIC" in DEFAULT_MAJOR_INDICES
    assert "^DJI" in DEFAULT_MAJOR_INDICES
    assert "^VIX" in DEFAULT_MAJOR_INDICES


@pytest.mark.asyncio
async def test_get_quote_returns_snapshot():
    """get_quote returns QuoteSnapshot from mocked _fetch_quote_sync."""
    expected = QuoteSnapshot(
        symbol="AAPL",
        name="Apple Inc.",
        price=185.0,
        change=2.0,
        change_percent=1.1,
        day_high=186.0,
        day_low=183.0,
        week_52_high=200.0,
        week_52_low=160.0,
        market_cap=None,
    )
    with patch("financial_advisor.market_data._fetch_quote_sync", return_value=expected):
        result = await get_quote("AAPL")
    assert result.symbol == "AAPL"
    assert result.price == 185.0


@pytest.mark.asyncio
async def test_get_multiple_quotes_returns_list():
    """get_multiple_quotes gathers multiple quotes (mocked _fetch_quote_sync)."""

    def fetch(symbol):
        return QuoteSnapshot(
            symbol, symbol, float(ord(symbol[0])), None, None, None, None, None, None, None
        )

    with patch("financial_advisor.market_data._fetch_quote_sync", side_effect=fetch):
        results = await get_multiple_quotes(["A", "B"])
    assert len(results) == 2
    assert results[0].symbol == "A"
    assert results[1].symbol == "B"


@pytest.mark.asyncio
async def test_get_index_quotes_uses_major_indices():
    """get_index_quotes calls get_multiple_quotes with keys from major_indices."""

    def fetch(symbol):
        return QuoteSnapshot(symbol, symbol, 100.0, None, None, None, None, None, None, None)

    with patch("financial_advisor.market_data._fetch_quote_sync", side_effect=fetch):
        results = await get_index_quotes({"^GSPC": "S&P 500", "^VIX": "VIX"})
    assert len(results) == 2
    assert {r.symbol for r in results} == {"^GSPC", "^VIX"}
