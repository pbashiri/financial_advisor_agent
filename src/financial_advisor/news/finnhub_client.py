"""Async Finnhub API client for financial news fetching."""

import logging
from datetime import datetime, timedelta

import httpx

from .models import NewsArticle

logger = logging.getLogger(__name__)

FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


class FinnhubClient:
    """Async client for the Finnhub REST API (news endpoints only)."""

    def __init__(self, api_key: str, base_url: str = FINNHUB_BASE_URL):
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url,
            params={"token": api_key},
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0),
        )

    async def get_company_news(
        self,
        symbol: str,
        days_back: int = 3,
    ) -> list[NewsArticle]:
        """Fetch recent company news for a ticker symbol.

        Args:
            symbol: Stock ticker (e.g. "AAPL").
            days_back: How many days of news to fetch (default 3).

        Returns:
            List of NewsArticle objects, newest first.
        """
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        try:
            resp = await self._client.get(
                "/company-news",
                params={"symbol": symbol.upper(), "from": from_date, "to": to_date},
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("Finnhub rate limit hit for %s", symbol)
            else:
                logger.warning("Finnhub HTTP error for %s: %s", symbol, e)
            return []
        except httpx.HTTPError as e:
            logger.warning("Finnhub request failed for %s: %s", symbol, e)
            return []

        return self._parse_articles(data, symbol)

    async def get_general_news(self, category: str = "general") -> list[NewsArticle]:
        """Fetch general market news.

        Args:
            category: News category (default "general").

        Returns:
            List of NewsArticle objects.
        """
        try:
            resp = await self._client.get("/news", params={"category": category})
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            logger.warning("Finnhub general news error: %s", e)
            return []

        return self._parse_articles(data, symbol="MARKET", category="general")

    def _parse_articles(
        self,
        raw: list[dict],
        symbol: str,
        category: str = "company",
    ) -> list[NewsArticle]:
        """Parse Finnhub JSON response into NewsArticle models."""
        articles = []
        for item in raw:
            try:
                article_id = str(item.get("id", ""))
                if not article_id:
                    continue

                published_ts = item.get("datetime", 0)
                published_at = datetime.fromtimestamp(published_ts)

                articles.append(
                    NewsArticle(
                        article_id=article_id,
                        symbol=symbol.upper(),
                        headline=item.get("headline", ""),
                        summary=item.get("summary", ""),
                        source=item.get("source", ""),
                        url=item.get("url", ""),
                        published_at=published_at,
                        category=category,
                    )
                )
            except Exception as e:
                logger.debug("Skipping malformed Finnhub article: %s", e)
                continue

        return articles

    async def close(self) -> None:
        await self._client.aclose()
