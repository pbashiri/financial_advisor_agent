"""Tests for the LangGraph trade recommendation workflow."""

from dataclasses import asdict
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from financial_advisor.market_data import QuoteSnapshot
from financial_advisor.portfolio.models import (
    AllocationItem,
    Holding,
    PortfolioSummary,
)
from financial_advisor.workflows.nodes import (
    analyze_fundamentals,
    analyze_technicals,
    assess_portfolio_impact,
    fetch_market_data,
    fetch_portfolio_context,
    format_recommendation,
    generate_recommendation,
    retrieve_news,
)
from financial_advisor.workflows.state import RecommendationState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_QUOTE = QuoteSnapshot(
    symbol="AAPL",
    name="Apple Inc",
    price=195.50,
    change=3.20,
    change_percent=1.66,
    day_high=196.00,
    day_low=192.00,
    week_52_high=220.00,
    week_52_low=150.00,
    market_cap=3_000_000_000_000,
)


def _mock_claude_response(text: str):
    """Create a mock Claude API response."""
    mock_resp = MagicMock()
    mock_resp.content = [MagicMock(text=text)]
    return mock_resp


def _base_state(**overrides) -> RecommendationState:
    """Create a base state with defaults."""
    state = {
        "symbol": "AAPL",
        "user_id": 12345,
        "errors": [],
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# fetch_market_data tests
# ---------------------------------------------------------------------------


async def test_fetch_market_data_success():
    """fetch_market_data populates quote from yfinance."""
    state = _base_state()

    with patch("financial_advisor.workflows.nodes.get_quote", return_value=MOCK_QUOTE):
        result = await fetch_market_data(state)

    assert result["quote"]["symbol"] == "AAPL"
    assert result["quote"]["price"] == 195.50
    assert result["errors"] == []


async def test_fetch_market_data_with_error():
    """fetch_market_data handles quote errors gracefully."""
    error_quote = QuoteSnapshot(
        symbol="AAPL",
        name="AAPL",
        price=None,
        change=None,
        change_percent=None,
        day_high=None,
        day_low=None,
        week_52_high=None,
        week_52_low=None,
        market_cap=None,
        error="Network error",
    )
    state = _base_state()

    with patch("financial_advisor.workflows.nodes.get_quote", return_value=error_quote):
        result = await fetch_market_data(state)

    assert result["quote"]["error"] == "Network error"
    assert len(result["errors"]) == 1


# ---------------------------------------------------------------------------
# fetch_portfolio_context tests
# ---------------------------------------------------------------------------


async def test_fetch_portfolio_context_with_holdings():
    """fetch_portfolio_context loads holdings and computes summary."""
    storage = AsyncMock()
    storage.get_holdings.return_value = [
        Holding(symbol="AAPL", shares=10, cost_basis=150.0),
        Holding(symbol="MSFT", shares=5, cost_basis=300.0),
    ]

    state = _base_state()

    with patch(
        "financial_advisor.market_data.get_multiple_quotes",
        return_value=[MOCK_QUOTE, MOCK_QUOTE],
    ):
        result = await fetch_portfolio_context(state, portfolio_storage=storage)

    assert len(result["holdings"]) == 2
    assert result["portfolio_summary"] is not None
    assert result["errors"] == []


async def test_fetch_portfolio_context_empty():
    """fetch_portfolio_context handles empty portfolio."""
    storage = AsyncMock()
    storage.get_holdings.return_value = []

    state = _base_state()
    result = await fetch_portfolio_context(state, portfolio_storage=storage)

    assert result["holdings"] == []
    assert result["portfolio_summary"] is None


# ---------------------------------------------------------------------------
# retrieve_news tests
# ---------------------------------------------------------------------------


async def test_retrieve_news_with_results():
    """retrieve_news returns articles from vector store."""
    embedder = AsyncMock()
    embedder.embed.return_value = [0.1, 0.2, 0.3]

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "article_id": "a1",
        "symbol": "AAPL",
        "headline": "Apple launches new product",
        "source": "Reuters",
    }

    store = MagicMock()
    store.search.return_value = [mock_result]

    state = _base_state()
    result = await retrieve_news(state, vector_store=store, embedder=embedder)

    assert len(result["news_articles"]) == 1
    assert result["errors"] == []


async def test_retrieve_news_no_store():
    """retrieve_news returns empty when no vector store available."""
    state = _base_state()
    result = await retrieve_news(state, vector_store=None, embedder=None)

    assert result["news_articles"] == []


# ---------------------------------------------------------------------------
# Analysis node tests
# ---------------------------------------------------------------------------


async def test_analyze_technicals():
    """analyze_technicals calls Claude and returns analysis."""
    client = AsyncMock()
    client.messages.create.return_value = _mock_claude_response(
        "AAPL is trading near its 52-week high with strong momentum."
    )

    state = _base_state(quote=asdict(MOCK_QUOTE))
    result = await analyze_technicals(state, client=client, model="test-model")

    assert "AAPL" in result["technical_analysis"]
    assert result["errors"] == []
    client.messages.create.assert_called_once()


async def test_analyze_technicals_no_quote():
    """analyze_technicals handles missing quote data."""
    client = AsyncMock()
    state = _base_state(quote=None)

    result = await analyze_technicals(state, client=client, model="test-model")

    assert "unavailable" in result["technical_analysis"].lower()
    client.messages.create.assert_not_called()


async def test_analyze_fundamentals_with_news():
    """analyze_fundamentals uses news context in Claude prompt."""
    client = AsyncMock()
    client.messages.create.return_value = _mock_claude_response(
        "Recent news suggests positive sentiment for AAPL."
    )

    state = _base_state(
        news_articles=[
            {"headline": "Apple beats earnings", "source": "Reuters"},
            {"headline": "New iPhone launched", "source": "Bloomberg"},
        ]
    )
    result = await analyze_fundamentals(state, client=client, model="test-model")

    assert "AAPL" in result["fundamental_context"] or "positive" in result["fundamental_context"]
    assert result["errors"] == []


async def test_assess_portfolio_impact():
    """assess_portfolio_impact analyzes position within portfolio."""
    client = AsyncMock()
    client.messages.create.return_value = _mock_claude_response(
        "Adding AAPL would increase tech concentration."
    )

    summary = PortfolioSummary(
        total_value=100000,
        total_cost=90000,
        total_gain=10000,
        gain_pct=11.1,
        holdings=[],
        allocation=[
            AllocationItem(
                symbol="AAPL",
                name="Apple",
                value=50000,
                pct_of_portfolio=50.0,
                account_type="brokerage",
            ),
        ],
        as_of=datetime.now(),
    )

    state = _base_state(portfolio_summary=summary.model_dump())
    result = await assess_portfolio_impact(state, client=client, model="test-model")

    assert result["portfolio_impact"] is not None
    assert result["errors"] == []


# ---------------------------------------------------------------------------
# generate_recommendation tests
# ---------------------------------------------------------------------------


async def test_generate_recommendation_parses_json():
    """generate_recommendation parses Claude's JSON output."""
    rec_json = (
        '{"action": "BUY", "confidence": "HIGH",'
        ' "reasoning": "Strong fundamentals.",'
        ' "risk_factors": ["Market volatility"]}'
    )

    client = AsyncMock()
    client.messages.create.return_value = _mock_claude_response(rec_json)

    state = _base_state(
        technical_analysis="Trading near highs.",
        fundamental_context="Strong earnings.",
        portfolio_impact="Would increase tech exposure.",
    )

    result = await generate_recommendation(state, client=client, model="test-model")

    assert result["action"] == "BUY"
    assert result["confidence"] == "HIGH"
    assert "Strong" in result["reasoning"]
    assert len(result["risk_factors"]) == 1


async def test_generate_recommendation_handles_markdown_json():
    """generate_recommendation handles JSON wrapped in markdown code blocks."""
    rec_json = (
        '```json\n{"action": "HOLD", "confidence": "MEDIUM",'
        ' "reasoning": "Wait and see.",'
        ' "risk_factors": []}\n```'
    )

    client = AsyncMock()
    client.messages.create.return_value = _mock_claude_response(rec_json)

    state = _base_state()
    result = await generate_recommendation(state, client=client, model="test-model")

    assert result["action"] == "HOLD"
    assert result["confidence"] == "MEDIUM"


async def test_generate_recommendation_handles_failure():
    """generate_recommendation falls back to HOLD on error."""
    client = AsyncMock()
    client.messages.create.side_effect = Exception("API error")

    state = _base_state()
    result = await generate_recommendation(state, client=client, model="test-model")

    assert result["action"] == "HOLD"
    assert result["confidence"] == "LOW"
    assert len(result["errors"]) == 1


# ---------------------------------------------------------------------------
# format_recommendation tests
# ---------------------------------------------------------------------------


def test_format_recommendation_full():
    """format_recommendation creates a formatted Telegram message."""
    state = _base_state(
        quote=asdict(MOCK_QUOTE),
        action="BUY",
        confidence="HIGH",
        reasoning="Strong technicals and positive news.",
        risk_factors=["Market volatility", "Valuation concerns"],
    )

    result = format_recommendation(state)

    text = result["recommendation_text"]
    assert "AAPL" in text
    assert "BUY" in text
    assert "HIGH" in text
    assert "Strong technicals" in text
    assert "Market volatility" in text
    assert "$195.50" in text


def test_format_recommendation_no_quote():
    """format_recommendation handles missing quote data."""
    state = _base_state(
        quote=None,
        action="HOLD",
        confidence="LOW",
        reasoning="Insufficient data.",
        risk_factors=[],
    )

    result = format_recommendation(state)
    text = result["recommendation_text"]
    assert "AAPL" in text
    assert "HOLD" in text
    assert "N/A" in text


def test_format_recommendation_with_errors():
    """format_recommendation shows error count note."""
    state = _base_state(
        quote=asdict(MOCK_QUOTE),
        action="HOLD",
        confidence="LOW",
        reasoning="Partial analysis.",
        risk_factors=[],
        errors=["News retrieval failed", "Portfolio unavailable"],
    )

    result = format_recommendation(state)
    assert "2 issue(s)" in result["recommendation_text"]
