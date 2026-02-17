"""Tests for portfolio storage and CSV import."""

from pathlib import Path

import pytest

from financial_advisor.portfolio.csv_import import parse_holdings_csv
from financial_advisor.portfolio.models import Holding
from financial_advisor.portfolio.storage import PortfolioStorage


# --- Storage tests ---


@pytest.fixture
async def storage(tmp_path: Path):
    db_path = tmp_path / "test_portfolio.db"
    store = PortfolioStorage(db_path)
    await store.initialize()
    yield store
    await store.close()


async def test_storage_empty_on_init(storage: PortfolioStorage):
    holdings = await storage.get_holdings()
    assert holdings == []


async def test_upsert_and_get_holding(storage: PortfolioStorage):
    h = Holding(symbol="AAPL", shares=10.0, cost_basis=150.0, account_type="brokerage")
    await storage.upsert_holding(h)

    holdings = await storage.get_holdings()
    assert len(holdings) == 1
    assert holdings[0].symbol == "AAPL"
    assert holdings[0].shares == 10.0
    assert holdings[0].cost_basis == 150.0


async def test_upsert_updates_existing(storage: PortfolioStorage):
    h1 = Holding(symbol="AAPL", shares=10.0, cost_basis=150.0)
    await storage.upsert_holding(h1)

    h2 = Holding(symbol="AAPL", shares=20.0, cost_basis=160.0)
    await storage.upsert_holding(h2)

    holdings = await storage.get_holdings()
    assert len(holdings) == 1
    assert holdings[0].shares == 20.0
    assert holdings[0].cost_basis == 160.0


async def test_delete_holding(storage: PortfolioStorage):
    await storage.upsert_holding(Holding(symbol="VOO", shares=5.0, cost_basis=400.0))
    deleted = await storage.delete_holding("VOO")
    assert deleted is True
    assert await storage.get_holdings() == []


async def test_delete_nonexistent_returns_false(storage: PortfolioStorage):
    deleted = await storage.delete_holding("UNKNOWN")
    assert deleted is False


async def test_seed_from_profile(storage: PortfolioStorage):
    profile_data = [
        {"symbol": "AAPL", "shares": 50, "cost_basis": 150.0, "notes": "Core tech"},
        {"symbol": "VOO", "shares": 100, "cost_basis": 380.0},
        {"symbol": "", "shares": 10, "cost_basis": 100.0},  # invalid — empty symbol
    ]
    inserted = await storage.seed_from_profile(profile_data)
    assert inserted == 2  # 3 items minus 1 invalid

    holdings = await storage.get_holdings()
    symbols = {h.symbol for h in holdings}
    assert symbols == {"AAPL", "VOO"}


async def test_seed_skips_if_holdings_exist(storage: PortfolioStorage):
    await storage.upsert_holding(Holding(symbol="MSFT", shares=5.0, cost_basis=300.0))
    inserted = await storage.seed_from_profile([
        {"symbol": "AAPL", "shares": 10, "cost_basis": 150.0}
    ])
    assert inserted == 0  # table not empty, seeding skipped


async def test_multiple_holdings_ordered_by_symbol(storage: PortfolioStorage):
    for sym in ["VOO", "AAPL", "MSFT"]:
        await storage.upsert_holding(Holding(symbol=sym, shares=1.0, cost_basis=100.0))

    holdings = await storage.get_holdings()
    assert [h.symbol for h in holdings] == ["AAPL", "MSFT", "VOO"]


# --- CSV import tests ---


def test_csv_parse_basic():
    csv = "symbol,shares,cost_basis\nAAPL,50,150.00\nVOO,100,380.00\n"
    result = parse_holdings_csv(csv)
    assert len(result.holdings) == 2
    assert result.errors == []
    assert result.skipped == 0
    assert result.holdings[0].symbol == "AAPL"
    assert result.holdings[0].shares == 50.0
    assert result.holdings[0].cost_basis == 150.0


def test_csv_parse_with_optional_columns():
    csv = "symbol,shares,cost_basis,account_type,notes\nVTI,75,200.00,roth_ira,Index fund\n"
    result = parse_holdings_csv(csv)
    assert len(result.holdings) == 1
    assert result.holdings[0].account_type == "roth_ira"
    assert result.holdings[0].notes == "Index fund"


def test_csv_parse_normalizes_symbol_case():
    csv = "symbol,shares,cost_basis\naapl,10,150.00\n"
    result = parse_holdings_csv(csv)
    assert result.holdings[0].symbol == "AAPL"


def test_csv_parse_missing_required_column():
    csv = "symbol,shares\nAAPL,10\n"  # missing cost_basis
    result = parse_holdings_csv(csv)
    assert len(result.holdings) == 0
    assert any("cost_basis" in e for e in result.errors)


def test_csv_parse_invalid_shares():
    csv = "symbol,shares,cost_basis\nAAPL,not_a_number,150.00\n"
    result = parse_holdings_csv(csv)
    assert result.skipped == 1
    assert len(result.errors) == 1


def test_csv_parse_empty_symbol():
    csv = "symbol,shares,cost_basis\n,10,150.00\n"
    result = parse_holdings_csv(csv)
    assert result.skipped == 1


def test_csv_parse_negative_shares():
    csv = "symbol,shares,cost_basis\nAAPL,-10,150.00\n"
    result = parse_holdings_csv(csv)
    assert result.skipped == 1
    assert any("AAPL" in e for e in result.errors)


def test_csv_parse_empty_content():
    result = parse_holdings_csv("")
    assert len(result.holdings) == 0
    assert len(result.errors) > 0


def test_csv_parse_mixed_valid_invalid():
    csv = (
        "symbol,shares,cost_basis\n"
        "AAPL,50,150.00\n"          # valid
        ",10,100.00\n"              # invalid: empty symbol
        "VOO,abc,380.00\n"          # invalid: bad shares
        "MSFT,30,280.00\n"          # valid
    )
    result = parse_holdings_csv(csv)
    assert len(result.holdings) == 2
    assert result.skipped == 2
    symbols = {h.symbol for h in result.holdings}
    assert symbols == {"AAPL", "MSFT"}
