"""Tests for the ChromaDB vector store wrapper."""

import uuid
from datetime import datetime

from financial_advisor.news.models import EmbeddedArticle, NewsArticle
from financial_advisor.news.vector_store import NewsVectorStore

EMBEDDING_A = [0.1, 0.2, 0.3, 0.4, 0.5]
EMBEDDING_B = [0.9, 0.8, 0.7, 0.6, 0.5]
EMBEDDING_C = [0.5, 0.5, 0.5, 0.5, 0.5]


def _unique_store() -> NewsVectorStore:
    """Create an isolated ephemeral store with a unique collection name."""
    return NewsVectorStore.ephemeral(collection_name=f"test_{uuid.uuid4().hex[:8]}")


def _make_embedded(
    article_id: str = "art_1",
    symbol: str = "AAPL",
    headline: str = "Test headline",
    summary: str = "Test summary",
    embedding: list[float] | None = None,
    published_at: datetime | None = None,
) -> EmbeddedArticle:
    return EmbeddedArticle(
        article=NewsArticle(
            article_id=article_id,
            symbol=symbol,
            headline=headline,
            summary=summary,
            source="TestSource",
            url="https://example.com",
            published_at=published_at or datetime(2024, 2, 19, 12, 0),
            category="company",
        ),
        embedding=embedding or EMBEDDING_A,
    )


def test_add_and_count():
    """Adding articles increases the collection count."""
    store = _unique_store()
    assert store.count == 0

    added = store.add_articles([_make_embedded("a1"), _make_embedded("a2")])
    assert added == 2
    assert store.count == 2


def test_add_empty_list():
    """Adding empty list returns 0."""
    store = _unique_store()
    assert store.add_articles([]) == 0


def test_dedup_prevents_duplicate():
    """Adding the same article_id twice only stores once."""
    store = _unique_store()

    store.add_articles([_make_embedded("dup_1")])
    assert store.count == 1

    store.add_articles([_make_embedded("dup_1")])
    assert store.count == 1


def test_article_exists():
    """article_exists returns True for stored articles, False otherwise."""
    store = _unique_store()

    assert store.article_exists("missing") is False

    store.add_articles([_make_embedded("present")])
    assert store.article_exists("present") is True
    assert store.article_exists("absent") is False


def test_search_returns_results():
    """Search finds relevant articles by embedding similarity."""
    store = _unique_store()

    store.add_articles(
        [
            _make_embedded("a1", "AAPL", "Apple stock rises", embedding=EMBEDDING_A),
            _make_embedded("a2", "MSFT", "Microsoft earnings", embedding=EMBEDDING_B),
        ]
    )

    results = store.search(query_embedding=EMBEDDING_A, n_results=2)
    assert len(results) == 2
    # First result should be closest to EMBEDDING_A
    assert results[0].article_id == "a1"


def test_search_filters_by_symbol():
    """Search with symbol filter only returns matching articles."""
    store = _unique_store()

    store.add_articles(
        [
            _make_embedded("a1", "AAPL", "Apple news", embedding=EMBEDDING_A),
            _make_embedded("a2", "MSFT", "Microsoft news", embedding=EMBEDDING_B),
        ]
    )

    results = store.search(query_embedding=EMBEDDING_C, symbol="AAPL", n_results=5)
    assert len(results) == 1
    assert results[0].symbol == "AAPL"


def test_search_empty_store():
    """Search on empty store returns empty list."""
    store = _unique_store()
    results = store.search(query_embedding=EMBEDDING_A)
    assert results == []


def test_get_recent_returns_articles():
    """get_recent returns articles within the time window."""
    store = _unique_store()

    store.add_articles([_make_embedded("r1", "AAPL", "Recent news", published_at=datetime.now())])

    results = store.get_recent("AAPL", hours=24)
    assert len(results) == 1
    assert results[0].article_id == "r1"


def test_get_recent_filters_old_articles():
    """get_recent excludes articles outside the time window."""
    store = _unique_store()

    store.add_articles(
        [_make_embedded("old_1", "AAPL", "Old news", published_at=datetime(2020, 1, 1))]
    )

    results = store.get_recent("AAPL", hours=24)
    assert len(results) == 0
