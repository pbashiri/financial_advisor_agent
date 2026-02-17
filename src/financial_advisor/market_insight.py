"""Market insight from free APIs: Alpha Vantage (MCP-friendly) and Finnhub.

Alpha Vantage: https://www.alphavantage.co/ (free 25 req/day; official MCP: https://mcp.alphavantage.co/)
Finnhub: https://finnhub.io/ (free tier, 60 calls/min)
"""

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

ALPHA_VANTAGE_BASE = "https://www.alphavantage.co/query"
FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/news"


@dataclass
class MarketInsightResult:
    """Combined market insight from optional Alpha Vantage and Finnhub."""

    alpha_vantage_summary: str | None = None
    finnhub_summary: str | None = None

    def has_any(self) -> bool:
        return bool(self.alpha_vantage_summary or self.finnhub_summary)

    def to_briefing_text(self) -> str:
        parts = []
        if self.alpha_vantage_summary:
            parts.append(f"*Alpha Vantage (market news/sentiment)*\n{self.alpha_vantage_summary}")
        if self.finnhub_summary:
            parts.append(f"*Finnhub (market news)*\n{self.finnhub_summary}")
        return "\n\n".join(parts) if parts else ""


async def fetch_alpha_vantage_news(api_key: str, limit: int = 5) -> str | None:
    """Fetch recent market news/sentiment from Alpha Vantage (free tier: 25 req/day).

    Uses NEWS_SENTIMENT; no tickers = general market news. Returns a short summary
    string or None on failure (e.g. premium required, rate limit).
    """
    params = {
        "function": "NEWS_SENTIMENT",
        "limit": min(limit, 50),
        "apikey": api_key,
        "sort": "LATEST",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(ALPHA_VANTAGE_BASE, params=params)
            r.raise_for_status()
            data = r.json()
    except (httpx.HTTPError, Exception) as e:
        logger.warning("Alpha Vantage request failed: %s", e)
        return None

    feed = data.get("feed")
    if not feed or not isinstance(feed, list):
        # May be {"Note": "Premium endpoint"} or similar
        if data.get("Note"):
            logger.debug("Alpha Vantage: %s", data.get("Note"))
        return None

    lines = []
    for i, item in enumerate(feed[:5]):
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        if not title:
            continue
        source = (item.get("source", "") or "").strip()
        sentiment = item.get("overall_sentiment_label") or ""
        if sentiment:
            line = f"  • {title}"
            if source:
                line += f" ({source})"
            line += f" — {sentiment}"
        else:
            line = f"  • {title}"
            if source:
                line += f" ({source})"
        lines.append(line)

    if not lines:
        return None
    return "\n".join(lines)


async def fetch_finnhub_news(api_key: str, category: str = "general", max_items: int = 5) -> str | None:
    """Fetch market news from Finnhub (free tier: 60 calls/min, US market).

    Returns a short summary of headlines or None on failure.
    """
    params = {"category": category, "token": api_key}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(FINNHUB_NEWS_URL, params=params)
            r.raise_for_status()
            items = r.json()
    except (httpx.HTTPError, Exception) as e:
        logger.warning("Finnhub request failed: %s", e)
        return None

    if not isinstance(items, list):
        return None

    lines = []
    for item in items[:max_items]:
        if not isinstance(item, dict):
            continue
        headline = (item.get("headline") or "").strip()
        if not headline:
            continue
        source = (item.get("source", "") or "").strip()
        line = f"  • {headline}"
        if source:
            line += f" ({source})"
        lines.append(line)

    if not lines:
        return None
    return "\n".join(lines)


async def fetch_market_insight(
    alpha_vantage_api_key: str | None = None,
    finnhub_api_key: str | None = None,
) -> MarketInsightResult:
    """Fetch market insight from both APIs when keys are provided. Never raises."""
    result = MarketInsightResult()

    if alpha_vantage_api_key:
        result.alpha_vantage_summary = await fetch_alpha_vantage_news(alpha_vantage_api_key, limit=5)

    if finnhub_api_key:
        result.finnhub_summary = await fetch_finnhub_news(finnhub_api_key, max_items=5)

    return result
