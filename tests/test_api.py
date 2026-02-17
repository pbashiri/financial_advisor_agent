"""Integration tests for FastAPI routes."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from financial_advisor.api.app import create_app
from financial_advisor.config import Settings


def _test_settings():
    return Settings(
        telegram_bot_token="test",
        anthropic_api_key="sk-test",
        allowed_user_ids=frozenset({1}),
        user_profile={},
        major_indices={"^GSPC": "S&P 500", "^VIX": "VIX"},
    )


@pytest.fixture
def client(tmp_path):
    """TestClient with temp DB; context manager so lifespan runs and app.state is set."""
    app = create_app(settings=_test_settings(), db_path=tmp_path / "api_test.db")
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_portfolio_get_holdings_empty(client):
    r = client.get("/portfolio")
    assert r.status_code == 200
    assert r.json() == []


def test_portfolio_upsert_and_get(client):
    r = client.post(
        "/portfolio",
        json={"symbol": "AAPL", "shares": 10.0, "cost_basis": 150.0},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["symbol"] == "AAPL"
    assert data["shares"] == 10.0

    r2 = client.get("/portfolio")
    assert r2.status_code == 200
    holdings = r2.json()
    assert len(holdings) == 1
    assert holdings[0]["symbol"] == "AAPL"


def test_portfolio_delete_holding(client):
    client.post("/portfolio", json={"symbol": "VOO", "shares": 5.0, "cost_basis": 400.0})
    r = client.delete("/portfolio/VOO")
    assert r.status_code == 204
    r2 = client.get("/portfolio")
    assert r2.json() == []


def test_portfolio_delete_nonexistent_returns_404(client):
    r = client.delete("/portfolio/NOTFOUND")
    assert r.status_code == 404


def test_portfolio_import_text(client):
    csv = "symbol,shares,cost_basis\nAAPL,50,150.00\nVOO,100,380.00\n"
    r = client.post(
        "/portfolio/import/text",
        content=csv.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] == 2
    assert data["skipped"] == 0

    r2 = client.get("/portfolio")
    assert len(r2.json()) == 2


def test_analytics_summary_empty(client):
    r = client.get("/analytics/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total_value"] == 0.0
    assert data["total_cost"] == 0.0
    assert data["holdings"] == []
    assert "as_of" in data


def test_analytics_summary_text_empty(client):
    r = client.get("/analytics/summary/text")
    assert r.status_code == 200
    data = r.json()
    assert "text" in data
    assert "No holdings" in data["text"] or "no holdings" in data["text"].lower()


def test_analytics_summary_with_holdings(client):
    client.post("/portfolio", json={"symbol": "AAPL", "shares": 10.0, "cost_basis": 100.0})
    with patch(
        "financial_advisor.api.routes.analytics.get_multiple_quotes",
        new_callable=AsyncMock,
    ) as m:
        from financial_advisor.market_data import QuoteSnapshot

        m.return_value = [
            QuoteSnapshot(
                symbol="AAPL",
                name="Apple Inc.",
                price=150.0,
                change=2.0,
                change_percent=1.35,
                day_high=152.0,
                day_low=148.0,
                week_52_high=200.0,
                week_52_low=120.0,
                market_cap=None,
            ),
        ]
        r = client.get("/analytics/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["total_value"] == 1500.0
    assert data["total_cost"] == 1000.0
    assert len(data["holdings"]) == 1


def test_market_quote_returns_quote_or_404(client):
    # Without mocking yfinance, we get real network call or cached data.
    # Use a symbol that might 404 or return data.
    r = client.get("/market/quote/AAPL")
    # Either 200 (success) or 404 (yfinance error)
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        data = r.json()
        assert "symbol" in data
        assert data["symbol"] == "AAPL"


def test_portfolio_import_text_invalid_csv_returns_400(client):
    """Import with only invalid rows returns 400 with error details."""
    r = client.post(
        "/portfolio/import/text",
        content="symbol,shares,cost_basis\n,10,100\n".encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )
    assert r.status_code == 400
    data = r.json()
    assert "errors" in data.get("detail", data)


def test_market_indices_returns_list(client):
    with patch("financial_advisor.api.routes.market.get_index_quotes", new_callable=AsyncMock) as m:
        from financial_advisor.market_data import QuoteSnapshot

        m.return_value = [
            QuoteSnapshot(
                symbol="^GSPC",
                name="S&P 500",
                price=5000.0,
                change=10.0,
                change_percent=0.2,
                day_high=5010.0,
                day_low=4990.0,
                week_52_high=5100.0,
                week_52_low=4500.0,
                market_cap=None,
            ),
        ]
        r = client.get("/market/indices")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["symbol"] == "^GSPC"
