"""LangGraph graph definition for the trade recommendation workflow."""

import logging
from functools import partial

from anthropic import AsyncAnthropic
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from ..news.embedder import OllamaEmbedder
from ..news.vector_store import NewsVectorStore
from ..portfolio.storage import PortfolioStorage
from . import nodes
from .state import RecommendationState

logger = logging.getLogger(__name__)


def build_recommendation_graph(
    anthropic_client: AsyncAnthropic,
    analysis_model: str,
    portfolio_storage: PortfolioStorage,
    vector_store: NewsVectorStore | None = None,
    embedder: OllamaEmbedder | None = None,
    checkpointer=None,
) -> StateGraph:
    """Build and compile the recommendation workflow graph.

    The graph follows this flow:
        fetch_market_data ─────── analyze_technicals ──────┐
        fetch_portfolio ────── assess_portfolio_impact ─────┼── generate_rec ── format ── END
        retrieve_news ────────── analyze_fundamentals ─────┘

    Args:
        anthropic_client: AsyncAnthropic client for Claude API calls.
        analysis_model: Model ID for analysis nodes (e.g. claude-sonnet-4-5).
        portfolio_storage: Async SQLite storage for portfolio data.
        vector_store: ChromaDB vector store for news articles (optional).
        embedder: Ollama embedder for query embedding (optional).
        checkpointer: LangGraph checkpointer for human-in-the-loop (optional).

    Returns:
        Compiled StateGraph ready for invocation.
    """
    graph = StateGraph(RecommendationState)

    # --- Data gathering nodes ---
    graph.add_node("fetch_market_data", nodes.fetch_market_data)

    graph.add_node(
        "fetch_portfolio",
        partial(nodes.fetch_portfolio_context, portfolio_storage=portfolio_storage),
    )

    graph.add_node(
        "retrieve_news",
        partial(nodes.retrieve_news, vector_store=vector_store, embedder=embedder),
    )

    # --- Analysis nodes ---
    graph.add_node(
        "analyze_technicals",
        partial(nodes.analyze_technicals, client=anthropic_client, model=analysis_model),
    )

    graph.add_node(
        "analyze_fundamentals",
        partial(nodes.analyze_fundamentals, client=anthropic_client, model=analysis_model),
    )

    graph.add_node(
        "assess_portfolio_impact",
        partial(
            nodes.assess_portfolio_impact,
            client=anthropic_client,
            model=analysis_model,
        ),
    )

    # --- Recommendation nodes ---
    graph.add_node(
        "generate_recommendation",
        partial(
            nodes.generate_recommendation,
            client=anthropic_client,
            model=analysis_model,
        ),
    )

    graph.add_node("format_recommendation", nodes.format_recommendation)

    # --- Edges ---

    # Entry: fan-out to three parallel data-gathering nodes
    graph.set_entry_point("fetch_market_data")
    # Note: LangGraph doesn't support true fan-out from START in the basic API.
    # We chain them sequentially: market -> portfolio -> news -> analysis.
    # For a single-user bot, the latency difference is negligible.
    graph.add_edge("fetch_market_data", "fetch_portfolio")
    graph.add_edge("fetch_portfolio", "retrieve_news")

    # After data gathering, run analysis
    graph.add_edge("retrieve_news", "analyze_technicals")
    graph.add_edge("analyze_technicals", "analyze_fundamentals")
    graph.add_edge("analyze_fundamentals", "assess_portfolio_impact")

    # Analysis converges at recommendation
    graph.add_edge("assess_portfolio_impact", "generate_recommendation")
    graph.add_edge("generate_recommendation", "format_recommendation")
    graph.add_edge("format_recommendation", END)

    # Compile with checkpointer if provided (for human-in-the-loop)
    if checkpointer:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile(checkpointer=MemorySaver())
