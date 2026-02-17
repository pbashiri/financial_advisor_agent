"""Tests for market data module."""

from financial_advisor.market_data import (
    MAJOR_INDICES,
    QuoteSnapshot,
    format_quote,
)

# We don't test actual yfinance API calls (network-dependent).
# Instead we test the formatting and data structures.


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


def test_major_indices_defined():
    assert "^GSPC" in MAJOR_INDICES
    assert "^IXIC" in MAJOR_INDICES
    assert "^DJI" in MAJOR_INDICES
    assert "^VIX" in MAJOR_INDICES
