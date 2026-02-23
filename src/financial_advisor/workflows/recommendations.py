"""High-level interface for generating trade recommendations."""

import logging
import time

from anthropic import AsyncAnthropic

from ..news.embedder import OllamaEmbedder
from ..news.vector_store import NewsVectorStore
from ..portfolio.storage import PortfolioStorage
from .graph import build_recommendation_graph
from .state import RecommendationState

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """Runs the LangGraph recommendation workflow and manages state."""

    def __init__(
        self,
        anthropic_client: AsyncAnthropic,
        analysis_model: str,
        portfolio_storage: PortfolioStorage,
        vector_store: NewsVectorStore | None = None,
        embedder: OllamaEmbedder | None = None,
    ):
        self._graph = build_recommendation_graph(
            anthropic_client=anthropic_client,
            analysis_model=analysis_model,
            portfolio_storage=portfolio_storage,
            vector_store=vector_store,
            embedder=embedder,
        )
        # Store pending recommendations for human-in-the-loop
        self._pending: dict[int, dict] = {}  # user_id -> {thread_id, state}

    async def generate(self, symbol: str, user_id: int) -> RecommendationState:
        """Run the full recommendation workflow for a symbol.

        Returns the final state containing the recommendation text.
        """
        thread_id = f"rec_{user_id}_{symbol}_{int(time.time())}"

        initial_state: RecommendationState = {
            "symbol": symbol.upper(),
            "user_id": user_id,
            "errors": [],
        }

        config = {"configurable": {"thread_id": thread_id}}

        logger.info(
            "Starting recommendation for %s (user=%d, thread=%s)", symbol, user_id, thread_id
        )

        result = await self._graph.ainvoke(initial_state, config=config)

        # Store for potential human-in-the-loop follow-up
        self._pending[user_id] = {
            "thread_id": thread_id,
            "symbol": symbol.upper(),
            "state": result,
        }

        logger.info(
            "Recommendation complete for %s: action=%s confidence=%s",
            symbol,
            result.get("action"),
            result.get("confidence"),
        )

        return result

    def get_pending(self, user_id: int) -> dict | None:
        """Get the pending recommendation for a user (if any)."""
        return self._pending.get(user_id)

    def clear_pending(self, user_id: int) -> None:
        """Clear the pending recommendation for a user."""
        self._pending.pop(user_id, None)
