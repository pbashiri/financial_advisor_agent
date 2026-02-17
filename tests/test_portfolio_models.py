"""Tests for portfolio Pydantic models."""

from datetime import datetime, timezone

import pytest

from financial_advisor.portfolio.models import (
    AllocationItem,
    Holding,
    HoldingWithValue,
    PortfolioSummary,
    Transaction,
)


def test_holding_symbol_uppercase():
    h = Holding(symbol="aapl", shares=10.0, cost_basis=150.0)
    assert h.symbol == "AAPL"


def test_holding_symbol_stripped():
    h = Holding(symbol="  VOO  ", shares=5.0, cost_basis=400.0)
    assert h.symbol == "VOO"


def test_holding_default_account_type():
    h = Holding(symbol="AAPL", shares=10.0, cost_basis=150.0)
    assert h.account_type == "brokerage"


def test_holding_invalid_shares_zero():
    with pytest.raises(ValueError, match="shares must be positive"):
        Holding(symbol="AAPL", shares=0, cost_basis=150.0)


def test_holding_invalid_shares_negative():
    with pytest.raises(ValueError, match="shares must be positive"):
        Holding(symbol="AAPL", shares=-1.0, cost_basis=150.0)


def test_holding_invalid_cost_basis():
    with pytest.raises(ValueError, match="cost_basis must be positive"):
        Holding(symbol="AAPL", shares=10.0, cost_basis=0)


def test_transaction_action_uppercase():
    t = Transaction(symbol="AAPL", action="buy", shares=10.0, price=150.0)
    assert t.action == "BUY"


def test_transaction_invalid_action():
    with pytest.raises(ValueError, match="action must be BUY or SELL"):
        Transaction(symbol="AAPL", action="HOLD", shares=10.0, price=150.0)


def test_allocation_item():
    a = AllocationItem(
        symbol="AAPL",
        name="Apple Inc.",
        value=1500.0,
        pct_of_portfolio=50.0,
        account_type="brokerage",
    )
    assert a.symbol == "AAPL"
    assert a.pct_of_portfolio == 50.0


def test_portfolio_summary():
    now = datetime.now(timezone.utc)
    s = PortfolioSummary(
        total_value=5000.0,
        total_cost=4000.0,
        total_gain=1000.0,
        gain_pct=25.0,
        holdings=[],
        allocation=[],
        as_of=now,
    )
    assert s.total_value == 5000.0
    assert s.gain_pct == 25.0
    assert s.as_of == now


def test_holding_with_value():
    h = HoldingWithValue(
        symbol="AAPL",
        shares=10.0,
        cost_basis=100.0,
        account_type="brokerage",
        current_value=1500.0,
        total_cost=1000.0,
        gain_loss=500.0,
        gain_loss_pct=50.0,
    )
    assert h.current_value == 1500.0
    assert h.gain_loss_pct == 50.0
