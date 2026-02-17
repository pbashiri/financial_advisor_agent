"""Tests for briefing module (with mocked market data and agent)."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from financial_advisor.briefing import NOTABLE_MOVE_THRESHOLD, generate_briefing
from financial_advisor.config import Settings
from financial_advisor.market_data import QuoteSnapshot


def _make_quote(symbol: str, name: str, price: float, change_pct: float = 0.0) -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol=symbol,
        name=name,
        price=price,
        change=price * change_pct / 100,
        change_percent=change_pct,
        day_high=price * 1.01,
        day_low=price * 0.99,
        week_52_high=price * 1.2,
        week_52_low=price * 0.8,
        market_cap=None,
    )


@pytest.fixture
def settings_with_profile(tmp_path: Path):
    """Minimal settings with user profile for briefing."""
    return Settings(
        telegram_bot_token="test",
        anthropic_api_key="sk-test",
        allowed_user_ids=frozenset({1}),
        user_profile={
            "holdings": [{"symbol": "AAPL", "shares": 10, "cost_basis": 150.0}],
            "watchlist": ["GOOGL"],
        },
        major_indices={"^GSPC": "S&P 500", "^VIX": "VIX"},
    )


@pytest.fixture
def settings_empty_profile(tmp_path: Path):
    """Settings with no holdings or watchlist."""
    return Settings(
        telegram_bot_token="test",
        anthropic_api_key="sk-test",
        allowed_user_ids=frozenset({1}),
        user_profile={},
        major_indices={"^GSPC": "S&P 500"},
    )


@pytest.mark.asyncio
async def test_generate_briefing_includes_date_and_sections(settings_empty_profile):
    index_quotes = [
        _make_quote("^GSPC", "S&P 500", 5000.0, 0.5),
    ]

    with (
        patch("financial_advisor.briefing.get_index_quotes", new_callable=AsyncMock) as m_index,
        patch("financial_advisor.briefing.get_multiple_quotes", new_callable=AsyncMock) as m_multi,
        patch("financial_advisor.briefing.FinancialAdvisorAgent") as mock_agent_cls,
    ):
        m_index.return_value = index_quotes
        m_multi.return_value = []
        mock_agent = AsyncMock()
        mock_agent.summarize = AsyncMock(return_value="Markets were mixed today.")
        mock_agent_cls.return_value = mock_agent

        text = await generate_briefing(settings_empty_profile, mock_agent)

    assert "Daily Market Briefing" in text
    assert "Major Indices" in text
    assert "S&P 500" in text or "^GSPC" in text
    assert "Market Summary" in text
    assert "Markets were mixed today." in text
    assert "Yahoo Finance" in text or "not financial advice" in text


@pytest.mark.asyncio
async def test_generate_briefing_includes_holdings_section(settings_with_profile):
    index_quotes = [_make_quote("^GSPC", "S&P 500", 5000.0)]
    holding_quotes = [
        _make_quote("AAPL", "Apple Inc.", 185.0, 1.0),
        _make_quote("GOOGL", "Alphabet", 140.0, -0.5),
    ]

    with (
        patch("financial_advisor.briefing.get_index_quotes", new_callable=AsyncMock) as m_index,
        patch("financial_advisor.briefing.get_multiple_quotes", new_callable=AsyncMock) as m_multi,
        patch("financial_advisor.briefing.FinancialAdvisorAgent") as mock_agent_cls,
    ):
        m_index.return_value = index_quotes
        m_multi.return_value = holding_quotes
        mock_agent = AsyncMock()
        mock_agent.summarize = AsyncMock(return_value="Summary.")
        mock_agent_cls.return_value = mock_agent

        text = await generate_briefing(settings_with_profile, mock_agent)

    assert "Your Holdings" in text
    assert "AAPL" in text
    assert "Watchlist" in text
    assert "GOOGL" in text or "Alphabet" in text


@pytest.mark.asyncio
async def test_generate_briefing_notable_moves_section(settings_empty_profile):
    """When a quote moves > NOTABLE_MOVE_THRESHOLD, it appears in Notable Moves."""
    index_quotes = [
        _make_quote("^GSPC", "S&P 500", 5000.0, 4.0),  # +4%
        _make_quote("^VIX", "VIX", 15.0, -5.0),  # -5%
    ]

    with (
        patch("financial_advisor.briefing.get_index_quotes", new_callable=AsyncMock) as m_index,
        patch("financial_advisor.briefing.get_multiple_quotes", new_callable=AsyncMock) as m_multi,
        patch("financial_advisor.briefing.FinancialAdvisorAgent") as mock_agent_cls,
    ):
        m_index.return_value = index_quotes
        m_multi.return_value = []
        mock_agent = AsyncMock()
        mock_agent.summarize = AsyncMock(return_value="Summary.")
        mock_agent_cls.return_value = mock_agent

        text = await generate_briefing(settings_empty_profile, mock_agent)

    assert "Notable Moves" in text
    assert "4.00" in text or "5.00" in text


def test_notable_move_threshold():
    assert NOTABLE_MOVE_THRESHOLD == 3.0
