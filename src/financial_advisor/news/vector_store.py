"""ChromaDB vector store for financial news articles."""

import logging
from datetime import datetime, timedelta

import chromadb

from .models import EmbeddedArticle, NewsSearchResult

logger = logging.getLogger(__name__)

COLLECTION_NAME = "financial_news"


class NewsVectorStore:
    """Persistent ChromaDB collection for embedded news articles."""

    def __init__(self, persist_path: str, collection_name: str = COLLECTION_NAME):
        self._client = chromadb.PersistentClient(path=persist_path)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @classmethod
    def ephemeral(cls, collection_name: str = COLLECTION_NAME) -> "NewsVectorStore":
        """Create an in-memory store (for testing)."""
        store = object.__new__(cls)
        store._client = chromadb.EphemeralClient()
        store._collection = store._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        return store

    def add_articles(self, articles: list[EmbeddedArticle]) -> int:
        """Add embedded articles to the collection, skipping duplicates.

        Returns:
            Number of articles actually added.
        """
        if not articles:
            return 0

        # Filter out articles that already exist
        new_articles = [a for a in articles if not self.article_exists(a.article.article_id)]
        if not new_articles:
            return 0

        ids = [a.article.article_id for a in new_articles]
        embeddings = [a.embedding for a in new_articles]
        documents = [a.article.text_for_embedding for a in new_articles]
        metadatas = [
            {
                "article_id": a.article.article_id,
                "symbol": a.article.symbol,
                "headline": a.article.headline,
                "source": a.article.source,
                "url": a.article.url,
                "published_at": a.article.published_at.isoformat(),
                "category": a.article.category,
            }
            for a in new_articles
        ]

        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info("Added %d articles to vector store", len(new_articles))
        return len(new_articles)

    def search(
        self,
        query_embedding: list[float],
        symbol: str | None = None,
        n_results: int = 5,
    ) -> list[NewsSearchResult]:
        """Search for relevant articles by embedding similarity.

        Args:
            query_embedding: The query vector.
            symbol: Optional filter to a specific ticker.
            n_results: Max results to return.

        Returns:
            List of NewsSearchResult sorted by relevance.
        """
        where = {"symbol": symbol} if symbol else None

        try:
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where,
                include=["metadatas", "distances", "documents"],
            )
        except Exception as e:
            logger.warning("Vector store search failed: %s", e)
            return []

        search_results = []
        if results and results["metadatas"] and results["metadatas"][0]:
            for i, meta in enumerate(results["metadatas"][0]):
                distance = results["distances"][0][i] if results["distances"] else 0.0
                doc = results["documents"][0][i] if results["documents"] else ""
                # Extract summary from the document (headline\n\nsummary)
                parts = doc.split("\n\n", 1) if doc else ["", ""]
                summary = parts[1] if len(parts) > 1 else ""

                search_results.append(
                    NewsSearchResult(
                        article_id=meta.get("article_id", ""),
                        symbol=meta.get("symbol", ""),
                        headline=meta.get("headline", ""),
                        summary=summary,
                        source=meta.get("source", ""),
                        url=meta.get("url", ""),
                        published_at=meta.get("published_at", ""),
                        distance=distance,
                    )
                )

        return search_results

    def article_exists(self, article_id: str) -> bool:
        """Check if an article is already stored (for dedup)."""
        try:
            result = self._collection.get(ids=[article_id], include=[])
            return len(result["ids"]) > 0
        except Exception:
            return False

    def get_recent(
        self,
        symbol: str,
        hours: int = 24,
    ) -> list[NewsSearchResult]:
        """Get recent articles for a symbol within the time window.

        Note: ChromaDB doesn't support range queries on metadata natively,
        so we fetch all for the symbol and filter in Python.
        """
        try:
            cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
            results = self._collection.get(
                where={"symbol": symbol},
                include=["metadatas", "documents"],
            )
        except Exception as e:
            logger.warning("Failed to get recent articles for %s: %s", symbol, e)
            return []

        articles = []
        if results and results["metadatas"]:
            for i, meta in enumerate(results["metadatas"]):
                published = meta.get("published_at", "")
                if published >= cutoff:
                    doc = results["documents"][i] if results["documents"] else ""
                    parts = doc.split("\n\n", 1) if doc else ["", ""]
                    summary = parts[1] if len(parts) > 1 else ""

                    articles.append(
                        NewsSearchResult(
                            article_id=meta.get("article_id", ""),
                            symbol=meta.get("symbol", ""),
                            headline=meta.get("headline", ""),
                            summary=summary,
                            source=meta.get("source", ""),
                            url=meta.get("url", ""),
                            published_at=published,
                        )
                    )

        # Sort newest first
        articles.sort(key=lambda a: a.published_at, reverse=True)
        return articles

    @property
    def count(self) -> int:
        """Total number of articles in the collection."""
        return self._collection.count()
