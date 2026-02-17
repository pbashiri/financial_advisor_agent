"""Market data endpoints."""

import logging

from fastapi import APIRouter, HTTPException

from ...market_data import QuoteSnapshot, get_index_quotes, get_quote

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/quote/{symbol}", response_model=QuoteSnapshot)
async def get_stock_quote(symbol: str):
    """Fetch a live quote for a single symbol."""
    q = await get_quote(symbol.upper())
    if q.error:
        raise HTTPException(status_code=404, detail=f"Could not fetch quote for {symbol}: {q.error}")
    return q


@router.get("/indices", response_model=list[QuoteSnapshot])
async def get_indices():
    """Return quotes for major market indices (S&P 500, NASDAQ, Dow, VIX)."""
    return await get_index_quotes()
