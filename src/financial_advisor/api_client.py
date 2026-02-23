"""Async HTTP client for the FastAPI backend.

Falls back gracefully if the API server is not running, so the bot
can still function in development without Docker.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 2.0   # seconds — fail fast if API is down
_READ_TIMEOUT = 30.0     # seconds — allow time for yfinance calls


class ApiClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(_READ_TIMEOUT, connect=_CONNECT_TIMEOUT),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def health(self) -> bool:
        """Return True if the API server is reachable."""
        try:
            client = await self._get_client()
            r = await client.get("/health")
            return r.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def get_portfolio_summary_text(self) -> str | None:
        """Fetch formatted portfolio summary text, or None if API unavailable."""
        try:
            client = await self._get_client()
            r = await client.get("/analytics/summary/text")
            r.raise_for_status()
            return r.json().get("text")
        except (httpx.ConnectError, httpx.TimeoutException):
            logger.warning("API server not reachable — falling back to direct yfinance")
            return None
        except Exception as e:
            logger.error("API error fetching portfolio summary: %s", e)
            return None

    async def get_portfolio_summary(self) -> dict[str, Any] | None:
        """Fetch raw portfolio summary dict, or None if API unavailable."""
        try:
            client = await self._get_client()
            r = await client.get("/analytics/summary")
            r.raise_for_status()
            return r.json()
        except (httpx.ConnectError, httpx.TimeoutException):
            logger.warning("API server not reachable")
            return None
        except Exception as e:
            logger.error("API error fetching portfolio summary: %s", e)
            return None

    async def import_csv_text(self, csv_content: str) -> dict[str, Any] | None:
        """Import holdings from CSV text. Returns result dict or None on failure."""
        try:
            client = await self._get_client()
            r = await client.post(
                "/portfolio/import/text",
                content=csv_content.encode("utf-8"),
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )
            r.raise_for_status()
            return r.json()
        except (httpx.ConnectError, httpx.TimeoutException):
            logger.warning("API server not reachable for CSV import")
            return None
        except Exception as e:
            logger.error("API error during CSV import: %s", e)
            return None

    async def get_quote(self, symbol: str) -> dict[str, Any] | None:
        """Fetch a single quote via the API."""
        try:
            client = await self._get_client()
            r = await client.get(f"/market/quote/{symbol}")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except (httpx.ConnectError, httpx.TimeoutException):
            return None
        except Exception as e:
            logger.error("API error fetching quote for %s: %s", symbol, e)
            return None

    async def get_portfolio_holdings(self) -> list[dict[str, Any]] | None:
        """Fetch portfolio holdings list, or None if API unavailable."""
        try:
            client = await self._get_client()
            r = await client.get("/portfolio")
            r.raise_for_status()
            return r.json()
        except (httpx.ConnectError, httpx.TimeoutException):
            logger.warning("API server not reachable")
            return None
        except Exception as e:
            logger.error("API error fetching portfolio holdings: %s", e)
            return None
