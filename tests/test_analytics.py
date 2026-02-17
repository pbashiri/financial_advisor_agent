"""Tests for portfolio analytics calculations."""

import pytest

from financial_advisor.market_data import QuoteSnapshot
from financial_advisor.portfolio.analytics import (
    calculate_summary,
    format_portfolio_summary,
    get_allocation,
)
from financial_advisor.portfolio.models import Holding, HoldingWithValue


def _make_quote(symbol: str, price: float, change_pct: float = 0.0) -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol=symbol,
        name=f"{symbol} Inc.",
        price=price,
        change=price * change_pct / 100,
        change_percent=change_pct,
        day_high=price * 1.01,
        day_low=price * 0.99,
        week_52_high=price * 1.2,
        week_52_low=price * 0.8,
        market_cap=None,
    )


def _make_unavailable_quote(symbol: str) -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol=symbol,
        name=symbol,
        price=None,
        change=None,
        change_percent=None,
        day_high=None,
        day_low=None,
        week_52_high=None,
        week_52_low=None,
        market_cap=None,
        error="Unavailable",
    )


# --- calculate_summary tests ---


def test_calculate_summary_basic():
    holdings = [
        Holding(symbol="AAPL", shares=10.0, cost_basis=100.0),
        Holding(symbol="VOO", shares=5.0, cost_basis=400.0),
    ]
    quotes = {
        "AAPL": _make_quote("AAPL", 150.0, 1.0),
        "VOO": _make_quote("VOO", 420.0, -0.5),
    }

    summary = calculate_summary(holdings, quotes)

    # AAPL: 10 * 150 = 1500, cost = 10 * 100 = 1000, gain = 500
    # VOO: 5 * 420 = 2100, cost = 5 * 400 = 2000, gain = 100
    assert summary.total_value == pytest.approx(3600.0)
    assert summary.total_cost == pytest.approx(3000.0)
    assert summary.total_gain == pytest.approx(600.0)
    assert summary.gain_pct == pytest.approx(20.0)
    assert len(summary.holdings) == 2
    assert len(summary.allocation) == 2


def test_calculate_summary_with_loss():
    holdings = [Holding(symbol="XYZ", shares=10.0, cost_basis=200.0)]
    quotes = {"XYZ": _make_quote("XYZ", 150.0)}

    summary = calculate_summary(holdings, quotes)

    assert summary.total_gain == pytest.approx(-500.0)
    assert summary.gain_pct == pytest.approx(-25.0)


def test_calculate_summary_unavailable_price():
    holdings = [
        Holding(symbol="AAPL", shares=10.0, cost_basis=100.0),
        Holding(symbol="BAD", shares=5.0, cost_basis=50.0),
    ]
    quotes = {
        "AAPL": _make_quote("AAPL", 150.0),
        "BAD": _make_unavailable_quote("BAD"),
    }

    summary = calculate_summary(holdings, quotes)

    # Only AAPL contributes to total_value
    assert summary.total_value == pytest.approx(1500.0)
    # total_cost includes BAD's cost even if price unavailable
    assert summary.total_cost == pytest.approx(1250.0)
    # Only AAPL in allocation (BAD has no value)
    assert len(summary.allocation) == 1
    assert summary.allocation[0].symbol == "AAPL"


def test_calculate_summary_empty_holdings():
    summary = calculate_summary([], {})
    assert summary.total_value == 0.0
    assert summary.total_cost == 0.0
    assert summary.total_gain == 0.0
    assert summary.gain_pct == 0.0
    assert summary.holdings == []
    assert summary.allocation == []


# --- get_allocation tests ---


def test_get_allocation_sorted_by_pct():
    holdings = [
        HoldingWithValue(
            symbol="AAPL",
            shares=10,
            cost_basis=100,
            account_type="brokerage",
            current_value=3000.0,
            total_cost=1000.0,
            gain_loss=2000.0,
            gain_loss_pct=200.0,
        ),
        HoldingWithValue(
            symbol="VOO",
            shares=5,
            cost_basis=400,
            account_type="brokerage",
            current_value=1000.0,
            total_cost=2000.0,
            gain_loss=-1000.0,
            gain_loss_pct=-50.0,
        ),
    ]
    quotes = {
        "AAPL": _make_quote("AAPL", 300.0),
        "VOO": _make_quote("VOO", 200.0),
    }

    allocation = get_allocation(holdings, total_value=4000.0, quotes=quotes)

    assert len(allocation) == 2
    # AAPL has 75%, VOO has 25%
    assert allocation[0].symbol == "AAPL"
    assert allocation[0].pct_of_portfolio == pytest.approx(75.0)
    assert allocation[1].symbol == "VOO"
    assert allocation[1].pct_of_portfolio == pytest.approx(25.0)


def test_get_allocation_skips_zero_value():
    holdings = [
        HoldingWithValue(
            symbol="AAPL",
            shares=10,
            cost_basis=100,
            account_type="brokerage",
            current_value=1000.0,
            total_cost=1000.0,
            gain_loss=0.0,
            gain_loss_pct=0.0,
        ),
        HoldingWithValue(
            symbol="BAD",
            shares=5,
            cost_basis=50,
            account_type="brokerage",
            current_value=None,
            total_cost=250.0,
            gain_loss=None,
            gain_loss_pct=None,
        ),
    ]
    quotes = {"AAPL": _make_quote("AAPL", 100.0), "BAD": _make_unavailable_quote("BAD")}

    allocation = get_allocation(holdings, total_value=1000.0, quotes=quotes)
    assert len(allocation) == 1
    assert allocation[0].symbol == "AAPL"


# --- format_portfolio_summary tests ---


def test_format_portfolio_summary_contains_key_info():
    holdings = [Holding(symbol="AAPL", shares=10.0, cost_basis=100.0)]
    quotes = {"AAPL": _make_quote("AAPL", 150.0, 1.5)}
    summary = calculate_summary(holdings, quotes)

    text = format_portfolio_summary(summary)

    assert "Portfolio Summary" in text
    assert "AAPL" in text
    assert "1,500.00" in text  # total value
    assert "+$500.00" in text  # gain
    assert "Allocation" in text
