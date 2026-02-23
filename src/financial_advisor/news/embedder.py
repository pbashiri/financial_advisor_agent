"""Ollama embedding wrapper for generating text embeddings locally."""

import logging

import httpx

logger = logging.getLogger(__name__)


class OllamaEmbedder:
    """Async client for Ollama's embedding API (POST /api/embed)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
    ):
        self._base_url = base_url
        self._model = model
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0),
        )

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string.

        Returns:
            Embedding vector as list of floats.

        Raises:
            RuntimeError: If Ollama is unreachable or returns an error.
        """
        try:
            resp = await self._client.post(
                "/api/embed",
                json={"model": self._model, "input": text},
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings")
            if not embeddings or not embeddings[0]:
                raise RuntimeError(f"Empty embedding response from Ollama: {data}")
            return embeddings[0]
        except httpx.HTTPError as e:
            raise RuntimeError(f"Ollama embedding failed: {e}") from e

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts using Ollama's batch support.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        try:
            resp = await self._client.post(
                "/api/embed",
                json={"model": self._model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if len(embeddings) != len(texts):
                raise RuntimeError(f"Expected {len(texts)} embeddings, got {len(embeddings)}")
            return embeddings
        except httpx.HTTPError as e:
            raise RuntimeError(f"Ollama batch embedding failed: {e}") from e

    async def health(self) -> bool:
        """Check if Ollama is running and responsive."""
        try:
            resp = await self._client.get("/")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        await self._client.aclose()
