"""News ingestion pipeline: fetch → dedup → embed → store."""

import asyncio
import logging
from dataclasses import dataclass, field

from .embedder import OllamaEmbedder
from .finnhub_client import FinnhubClient
from .models import EmbeddedArticle
from .vector_store import NewsVectorStore

logger = logging.getLogger(__name__)

# Delay between per-symbol API calls to stay within Finnhub rate limits
RATE_LIMIT_DELAY = 1.0


@dataclass
class IngestionStats:
    """Statistics from a single ingestion run."""

    symbols_processed: int = 0
    articles_fetched: int = 0
    articles_new: int = 0
    articles_skipped: int = 0
    articles_embedded: int = 0
    articles_stored: int = 0
    errors: list[str] = field(default_factory=list)


class NewsIngestionPipeline:
    """Orchestrates fetching, embedding, and storing financial news."""

    def __init__(
        self,
        finnhub: FinnhubClient,
        embedder: OllamaEmbedder,
        vector_store: NewsVectorStore,
    ):
        self._finnhub = finnhub
        self._embedder = embedder
        self._vector_store = vector_store

    async def ingest_for_symbols(
        self,
        symbols: list[str],
        days_back: int = 3,
    ) -> IngestionStats:
        """Fetch and embed news for the given ticker symbols.

        Processes symbols sequentially with rate-limit delays between calls.

        Args:
            symbols: List of ticker symbols (e.g. ["AAPL", "MSFT"]).
            days_back: How many days of news to fetch per symbol.

        Returns:
            IngestionStats with counts and errors.
        """
        stats = IngestionStats()

        for symbol in symbols:
            try:
                await self._ingest_symbol(symbol, days_back, stats)
            except Exception as e:
                error_msg = f"{symbol}: {e}"
                logger.error("Ingestion failed for %s: %s", symbol, e)
                stats.errors.append(error_msg)

            stats.symbols_processed += 1

            # Rate limit buffer between symbols
            if symbol != symbols[-1]:
                await asyncio.sleep(RATE_LIMIT_DELAY)

        logger.info(
            "Ingestion complete: %d symbols, %d fetched, %d new, %d stored, %d errors",
            stats.symbols_processed,
            stats.articles_fetched,
            stats.articles_new,
            stats.articles_stored,
            len(stats.errors),
        )
        return stats

    async def _ingest_symbol(
        self,
        symbol: str,
        days_back: int,
        stats: IngestionStats,
    ) -> None:
        """Fetch, dedup, embed, and store articles for a single symbol."""
        # 1. Fetch from Finnhub
        articles = await self._finnhub.get_company_news(symbol, days_back=days_back)
        stats.articles_fetched += len(articles)

        if not articles:
            logger.debug("No news articles for %s", symbol)
            return

        # 2. Dedup — filter out articles already in vector store
        new_articles = [a for a in articles if not self._vector_store.article_exists(a.article_id)]
        stats.articles_skipped += len(articles) - len(new_articles)
        stats.articles_new += len(new_articles)

        if not new_articles:
            logger.debug("All %d articles for %s already stored", len(articles), symbol)
            return

        # 3. Embed via Ollama (batch)
        texts = [a.text_for_embedding for a in new_articles]
        try:
            embeddings = await self._embedder.embed_batch(texts)
        except RuntimeError as e:
            logger.warning("Embedding failed for %s, skipping: %s", symbol, e)
            stats.errors.append(f"{symbol}: embedding failed — {e}")
            return

        stats.articles_embedded += len(embeddings)

        # 4. Package as EmbeddedArticle and store
        embedded = [
            EmbeddedArticle(article=article, embedding=emb)
            for article, emb in zip(new_articles, embeddings)
        ]
        stored = self._vector_store.add_articles(embedded)
        stats.articles_stored += stored

        logger.info(
            "%s: fetched=%d, new=%d, stored=%d",
            symbol,
            len(articles),
            len(new_articles),
            stored,
        )

    async def ingest_general_news(self) -> IngestionStats:
        """Fetch and embed general market news (not symbol-specific)."""
        stats = IngestionStats()
        stats.symbols_processed = 1

        try:
            articles = await self._finnhub.get_general_news()
            stats.articles_fetched = len(articles)

            if not articles:
                return stats

            new_articles = [
                a for a in articles if not self._vector_store.article_exists(a.article_id)
            ]
            stats.articles_skipped = len(articles) - len(new_articles)
            stats.articles_new = len(new_articles)

            if not new_articles:
                return stats

            texts = [a.text_for_embedding for a in new_articles]
            try:
                embeddings = await self._embedder.embed_batch(texts)
            except RuntimeError as e:
                stats.errors.append(f"general: embedding failed — {e}")
                return stats

            stats.articles_embedded = len(embeddings)

            embedded = [
                EmbeddedArticle(article=article, embedding=emb)
                for article, emb in zip(new_articles, embeddings)
            ]
            stored = self._vector_store.add_articles(embedded)
            stats.articles_stored = stored

        except Exception as e:
            logger.error("General news ingestion failed: %s", e)
            stats.errors.append(f"general: {e}")

        return stats
