"""Portfolio analytics endpoints."""

import logging

from fastapi import APIRouter, Request

from ...market_data import get_multiple_quotes
from ...portfolio.analytics import calculate_summary, format_portfolio_summary
from ...portfolio.models import PortfolioSummary
from ...portfolio.storage import PortfolioStorage

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_storage(request: Request) -> PortfolioStorage:
    return request.app.state.storage


@router.get("/summary", response_model=PortfolioSummary)
async def get_summary(request: Request):
    """Return full portfolio summary with live prices and analytics."""
    storage = _get_storage(request)
    holdings = await storage.get_holdings()

    if not holdings:
        from datetime import datetime, timezone

        return PortfolioSummary(
            total_value=0.0,
            total_cost=0.0,
            total_gain=0.0,
            gain_pct=0.0,
            holdings=[],
            allocation=[],
            as_of=datetime.now(timezone.utc),
        )

    symbols = [h.symbol for h in holdings]
    quotes_list = await get_multiple_quotes(symbols)
    quotes = {q.symbol: q for q in quotes_list}

    return calculate_summary(holdings, quotes)


@router.get("/summary/text")
async def get_summary_text(request: Request):
    """Return portfolio summary formatted as Telegram markdown."""
    storage = _get_storage(request)
    holdings = await storage.get_holdings()

    if not holdings:
        return {"text": "No holdings found. Import holdings via CSV or add them individually."}

    symbols = [h.symbol for h in holdings]
    quotes_list = await get_multiple_quotes(symbols)
    quotes = {q.symbol: q for q in quotes_list}

    summary = calculate_summary(holdings, quotes)
    return {"text": format_portfolio_summary(summary)}


@router.get("/allocation")
async def get_allocation(request: Request):
    """Return portfolio allocation breakdown."""
    storage = _get_storage(request)
    holdings = await storage.get_holdings()

    if not holdings:
        return {"allocation": []}

    symbols = [h.symbol for h in holdings]
    quotes_list = await get_multiple_quotes(symbols)
    quotes = {q.symbol: q for q in quotes_list}

    summary = calculate_summary(holdings, quotes)
    return {"allocation": [item.model_dump() for item in summary.allocation]}
