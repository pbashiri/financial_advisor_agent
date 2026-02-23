"""LangGraph state schema for trade recommendation workflows."""

from typing import Literal, TypedDict


class RecommendationState(TypedDict, total=False):
    """State that flows through the recommendation workflow graph.

    All fields are optional (total=False) since they get populated
    progressively as the workflow runs through nodes.
    """

    # Input (set at invocation)
    symbol: str
    user_id: int

    # Data gathering (populated by fetch nodes)
    quote: dict | None
    holdings: list[dict] | None
    portfolio_summary: dict | None
    news_articles: list[dict] | None

    # Analysis (populated by analysis nodes)
    technical_analysis: str | None
    fundamental_context: str | None
    portfolio_impact: str | None

    # Recommendation (populated by generate node)
    action: Literal["BUY", "SELL", "HOLD", "WATCH"] | None
    confidence: Literal["HIGH", "MEDIUM", "LOW"] | None
    reasoning: str | None
    risk_factors: list[str] | None

    # Output (populated by format node)
    recommendation_text: str | None

    # Human-in-the-loop
    user_decision: Literal["APPROVED", "REJECTED", "MORE_INFO"] | None
    followup_question: str | None

    # Error tracking
    errors: list[str]
