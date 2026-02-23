"""Pydantic models for news articles and search results."""

from datetime import datetime

from pydantic import BaseModel, Field


class NewsArticle(BaseModel):
    """A news article fetched from Finnhub."""

    article_id: str = Field(description="Unique article identifier from Finnhub")
    symbol: str = Field(description="Related ticker symbol")
    headline: str
    summary: str = ""
    source: str = ""
    url: str = ""
    published_at: datetime
    category: str = "company"  # "company" or "general"

    @property
    def text_for_embedding(self) -> str:
        """Concatenate headline + summary for embedding."""
        parts = [self.headline]
        if self.summary:
            parts.append(self.summary)
        return "\n\n".join(parts)


class EmbeddedArticle(BaseModel):
    """A news article with its embedding vector attached."""

    article: NewsArticle
    embedding: list[float]


class NewsSearchResult(BaseModel):
    """A search result from the vector store."""

    article_id: str
    symbol: str
    headline: str
    summary: str = ""
    source: str = ""
    url: str = ""
    published_at: str  # ISO string from metadata
    distance: float = 0.0  # cosine distance (lower = more similar)
