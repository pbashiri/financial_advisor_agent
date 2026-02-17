"""yfinance wrapper for market quotes and indices."""

import asyncio
import logging
from dataclasses import dataclass

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class QuoteSnapshot:
    symbol: str
    name: str
    price: float | None
    change: float | None
    change_percent: float | None
    day_high: float | None
    day_low: float | None
    week_52_high: float | None
    week_52_low: float | None
    market_cap: float | None
    error: str | None = None


def _fetch_quote_sync(symbol: str) -> QuoteSnapshot:
    """Fetch a single quote synchronously (called via asyncio.to_thread)."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        price = info.get("regularMarketPrice") or info.get("currentPrice")
        prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose")

        change = None
        change_pct = None
        if price is not None and prev_close:
            change = price - prev_close
            change_pct = (change / prev_close) * 100

        return QuoteSnapshot(
            symbol=symbol,
            name=info.get("shortName") or info.get("longName") or symbol,
            price=price,
            change=change,
            change_percent=change_pct,
            day_high=info.get("dayHigh") or info.get("regularMarketDayHigh"),
            day_low=info.get("dayLow") or info.get("regularMarketDayLow"),
            week_52_high=info.get("fiftyTwoWeekHigh"),
            week_52_low=info.get("fiftyTwoWeekLow"),
            market_cap=info.get("marketCap"),
        )
    except Exception as e:
        logger.warning("Failed to fetch quote for %s: %s", symbol, e)
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
            error=str(e),
        )


async def get_quote(symbol: str) -> QuoteSnapshot:
    """Fetch a single stock/index quote asynchronously."""
    return await asyncio.to_thread(_fetch_quote_sync, symbol)


async def get_multiple_quotes(symbols: list[str]) -> list[QuoteSnapshot]:
    """Fetch multiple quotes concurrently with graceful per-symbol failure."""
    tasks = [get_quote(s) for s in symbols]
    return await asyncio.gather(*tasks)


async def get_index_quotes(major_indices: dict[str, str]) -> list[QuoteSnapshot]:
    """Fetch major market index quotes. Symbols taken from major_indices (e.g. from settings)."""
    return await get_multiple_quotes(list(major_indices.keys()))


def format_quote(q: QuoteSnapshot) -> str:
    """Format a single quote for display."""
    if q.error or q.price is None:
        return f"  {q.symbol}: Data unavailable"

    arrow = "+" if (q.change or 0) >= 0 else ""
    change_str = f"{arrow}{q.change:.2f} ({arrow}{q.change_percent:.2f}%)" if q.change else "N/A"
    return f"  *{q.name}* ({q.symbol}): ${q.price:,.2f} | {change_str}"
