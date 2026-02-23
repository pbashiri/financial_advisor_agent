"""Tests for the Finnhub client, embedder, and ingestion pipeline."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from financial_advisor.news.embedder import OllamaEmbedder
from financial_advisor.news.finnhub_client import FinnhubClient
from financial_advisor.news.ingestion import NewsIngestionPipeline
from financial_advisor.news.models import EmbeddedArticle, NewsArticle
from financial_advisor.news.vector_store import NewsVectorStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_FINNHUB_RESPONSE = [
    {
        "category": "company news",
        "datetime": 1708300800,
        "headline": "Apple announces new product line",
        "id": 12345,
        "image": "https://example.com/img.jpg",
        "related": "AAPL",
        "source": "Reuters",
        "summary": "Apple Inc unveiled its latest products today.",
        "url": "https://example.com/article",
    },
    {
        "category": "company news",
        "datetime": 1708214400,
        "headline": "Apple earnings beat expectations",
        "id": 12346,
        "image": "",
        "related": "AAPL",
        "source": "Bloomberg",
        "summary": "Strong Q4 results for the tech giant.",
        "url": "https://example.com/article2",
    },
]

SAMPLE_EMBEDDING = [0.1, 0.2, 0.3, 0.4, 0.5]


def _make_article(article_id: str = "12345", symbol: str = "AAPL") -> NewsArticle:
    return NewsArticle(
        article_id=article_id,
        symbol=symbol,
        headline="Test headline",
        summary="Test summary",
        source="TestSource",
        url="https://example.com",
        published_at=datetime(2024, 2, 19),
        category="company",
    )


def _unique_store() -> NewsVectorStore:
    return NewsVectorStore.ephemeral(collection_name=f"test_{uuid.uuid4().hex[:8]}")


def _mock_response(status_code: int, json_data=None) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=json_data,
        request=httpx.Request("GET", "https://test"),
    )


# ---------------------------------------------------------------------------
# FinnhubClient tests
# ---------------------------------------------------------------------------


async def test_finnhub_parses_company_news():
    """Finnhub client correctly parses company news response."""
    client = FinnhubClient(api_key="test_key")
    client._client = AsyncMock(spec=httpx.AsyncClient)
    client._client.get = AsyncMock(return_value=_mock_response(200, SAMPLE_FINNHUB_RESPONSE))

    articles = await client.get_company_news("AAPL", days_back=3)

    assert len(articles) == 2
    assert articles[0].article_id == "12345"
    assert articles[0].symbol == "AAPL"
    assert articles[0].headline == "Apple announces new product line"
    assert articles[0].source == "Reuters"
    assert articles[1].article_id == "12346"


async def test_finnhub_handles_rate_limit():
    """Finnhub client returns empty list on 429 rate limit."""
    client = FinnhubClient(api_key="test_key")
    client._client = AsyncMock(spec=httpx.AsyncClient)
    client._client.get = AsyncMock(return_value=_mock_response(429))

    articles = await client.get_company_news("AAPL")
    assert articles == []


async def test_finnhub_handles_connection_error():
    """Finnhub client returns empty list on network error."""
    client = FinnhubClient(api_key="test_key")
    client._client = AsyncMock(spec=httpx.AsyncClient)
    client._client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    articles = await client.get_company_news("AAPL")
    assert articles == []


async def test_finnhub_skips_malformed_articles():
    """Finnhub client skips articles without an id."""
    data = [{"headline": "No ID article"}, SAMPLE_FINNHUB_RESPONSE[0]]
    client = FinnhubClient(api_key="test_key")
    client._client = AsyncMock(spec=httpx.AsyncClient)
    client._client.get = AsyncMock(return_value=_mock_response(200, data))

    articles = await client.get_company_news("AAPL")
    assert len(articles) == 1
    assert articles[0].article_id == "12345"


async def test_finnhub_general_news():
    """Finnhub client fetches general market news."""
    client = FinnhubClient(api_key="test_key")
    client._client = AsyncMock(spec=httpx.AsyncClient)
    client._client.get = AsyncMock(return_value=_mock_response(200, SAMPLE_FINNHUB_RESPONSE))

    articles = await client.get_general_news()
    assert len(articles) == 2
    assert articles[0].symbol == "MARKET"
    assert articles[0].category == "general"


# ---------------------------------------------------------------------------
# OllamaEmbedder tests
# ---------------------------------------------------------------------------


async def test_embedder_returns_vector():
    """Embedder returns embedding vector from Ollama."""
    embedder = OllamaEmbedder()
    mock_resp = httpx.Response(
        200,
        json={"embeddings": [SAMPLE_EMBEDDING]},
        request=httpx.Request("POST", "https://test"),
    )
    embedder._client = AsyncMock(spec=httpx.AsyncClient)
    embedder._client.post = AsyncMock(return_value=mock_resp)

    result = await embedder.embed("test text")
    assert result == SAMPLE_EMBEDDING


async def test_embedder_batch():
    """Embedder handles batch embedding."""
    batch_embeddings = [SAMPLE_EMBEDDING, [0.6, 0.7, 0.8, 0.9, 1.0]]
    embedder = OllamaEmbedder()
    mock_resp = httpx.Response(
        200,
        json={"embeddings": batch_embeddings},
        request=httpx.Request("POST", "https://test"),
    )
    embedder._client = AsyncMock(spec=httpx.AsyncClient)
    embedder._client.post = AsyncMock(return_value=mock_resp)

    result = await embedder.embed_batch(["text 1", "text 2"])
    assert len(result) == 2
    assert result[0] == SAMPLE_EMBEDDING


async def test_embedder_empty_batch():
    """Embedder returns empty list for empty input."""
    embedder = OllamaEmbedder()
    result = await embedder.embed_batch([])
    await embedder.close()
    assert result == []


async def test_embedder_handles_offline():
    """Embedder raises RuntimeError when Ollama is unreachable."""
    embedder = OllamaEmbedder()
    embedder._client = AsyncMock(spec=httpx.AsyncClient)
    embedder._client.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

    with pytest.raises(RuntimeError, match="Ollama"):
        await embedder.embed("test")


async def test_embedder_health_check():
    """Embedder health check returns True when Ollama is running."""
    embedder = OllamaEmbedder()
    mock_resp = httpx.Response(
        200, text="Ollama is running", request=httpx.Request("GET", "https://test")
    )
    embedder._client = AsyncMock(spec=httpx.AsyncClient)
    embedder._client.get = AsyncMock(return_value=mock_resp)

    assert await embedder.health() is True


async def test_embedder_health_check_offline():
    """Embedder health check returns False when Ollama is down."""
    embedder = OllamaEmbedder()
    embedder._client = AsyncMock(spec=httpx.AsyncClient)
    embedder._client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

    assert await embedder.health() is False


# ---------------------------------------------------------------------------
# Ingestion pipeline tests
# ---------------------------------------------------------------------------


async def test_ingestion_end_to_end():
    """Full pipeline: fetch -> dedup -> embed -> store."""
    finnhub = AsyncMock(spec=FinnhubClient)
    finnhub.get_company_news.return_value = [
        _make_article("a1"),
        _make_article("a2"),
    ]

    embedder = AsyncMock(spec=OllamaEmbedder)
    embedder.embed_batch.return_value = [SAMPLE_EMBEDDING, SAMPLE_EMBEDDING]

    store = _unique_store()

    pipeline = NewsIngestionPipeline(finnhub, embedder, store)
    stats = await pipeline.ingest_for_symbols(["AAPL"])

    assert stats.symbols_processed == 1
    assert stats.articles_fetched == 2
    assert stats.articles_new == 2
    assert stats.articles_stored == 2
    assert stats.errors == []
    assert store.count == 2


async def test_ingestion_dedup_skips_existing():
    """Pipeline skips articles already in vector store."""
    finnhub = AsyncMock(spec=FinnhubClient)
    finnhub.get_company_news.return_value = [
        _make_article("existing_1"),
        _make_article("new_1"),
    ]

    embedder = AsyncMock(spec=OllamaEmbedder)
    embedder.embed_batch.return_value = [SAMPLE_EMBEDDING]

    store = _unique_store()
    # Pre-populate one article
    store.add_articles(
        [EmbeddedArticle(article=_make_article("existing_1"), embedding=SAMPLE_EMBEDDING)]
    )

    pipeline = NewsIngestionPipeline(finnhub, embedder, store)
    stats = await pipeline.ingest_for_symbols(["AAPL"])

    assert stats.articles_fetched == 2
    assert stats.articles_skipped == 1
    assert stats.articles_new == 1
    assert stats.articles_stored == 1
    assert store.count == 2


async def test_ingestion_handles_embedding_failure():
    """Pipeline logs error and continues if Ollama fails."""
    finnhub = AsyncMock(spec=FinnhubClient)
    finnhub.get_company_news.return_value = [_make_article("a1")]

    embedder = AsyncMock(spec=OllamaEmbedder)
    embedder.embed_batch.side_effect = RuntimeError("Ollama down")

    store = _unique_store()

    pipeline = NewsIngestionPipeline(finnhub, embedder, store)
    stats = await pipeline.ingest_for_symbols(["AAPL"])

    assert stats.articles_fetched == 1
    assert stats.articles_stored == 0
    assert len(stats.errors) == 1
    assert "embedding failed" in stats.errors[0]


async def test_ingestion_no_articles():
    """Pipeline handles symbols with no news gracefully."""
    finnhub = AsyncMock(spec=FinnhubClient)
    finnhub.get_company_news.return_value = []

    embedder = AsyncMock(spec=OllamaEmbedder)
    store = _unique_store()

    pipeline = NewsIngestionPipeline(finnhub, embedder, store)
    stats = await pipeline.ingest_for_symbols(["XYZ"])

    assert stats.symbols_processed == 1
    assert stats.articles_fetched == 0
    assert stats.articles_stored == 0
    assert stats.errors == []
    embedder.embed_batch.assert_not_called()


async def test_ingestion_multiple_symbols():
    """Pipeline processes multiple symbols sequentially."""
    finnhub = AsyncMock(spec=FinnhubClient)
    finnhub.get_company_news.side_effect = [
        [_make_article("a1", "AAPL")],
        [_make_article("b1", "MSFT")],
    ]

    embedder = AsyncMock(spec=OllamaEmbedder)
    embedder.embed_batch.return_value = [SAMPLE_EMBEDDING]

    store = _unique_store()

    pipeline = NewsIngestionPipeline(finnhub, embedder, store)
    stats = await pipeline.ingest_for_symbols(["AAPL", "MSFT"])

    assert stats.symbols_processed == 2
    assert stats.articles_fetched == 2
    assert stats.articles_stored == 2
    assert store.count == 2
