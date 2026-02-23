"""Individual LangGraph node functions for the recommendation workflow."""

import json
import logging
from dataclasses import asdict

from anthropic import AsyncAnthropic

from ..market_data import get_quote
from ..news.vector_store import NewsVectorStore
from ..portfolio.analytics import calculate_summary
from ..portfolio.storage import PortfolioStorage
from .state import RecommendationState

logger = logging.getLogger(__name__)


async def fetch_market_data(state: RecommendationState) -> dict:
    """Fetch live market quote for the symbol."""
    symbol = state["symbol"]
    errors = list(state.get("errors", []))

    try:
        quote = await get_quote(symbol)
        if quote.error:
            errors.append(f"Quote error for {symbol}: {quote.error}")
        return {"quote": asdict(quote), "errors": errors}
    except Exception as e:
        errors.append(f"Failed to fetch quote for {symbol}: {e}")
        return {"quote": None, "errors": errors}


async def fetch_portfolio_context(
    state: RecommendationState,
    portfolio_storage: PortfolioStorage,
) -> dict:
    """Load current portfolio holdings and calculate summary."""
    errors = list(state.get("errors", []))

    try:
        holdings = await portfolio_storage.get_holdings()
        if not holdings:
            return {"holdings": [], "portfolio_summary": None, "errors": errors}

        # Fetch quotes for all holdings
        from ..market_data import get_multiple_quotes

        quotes_list = await get_multiple_quotes([h.symbol for h in holdings])
        quotes_dict = {q.symbol: q for q in quotes_list}

        summary = calculate_summary(holdings, quotes_dict)

        return {
            "holdings": [h.model_dump() for h in holdings],
            "portfolio_summary": summary.model_dump(),
            "errors": errors,
        }
    except Exception as e:
        errors.append(f"Failed to fetch portfolio: {e}")
        return {"holdings": None, "portfolio_summary": None, "errors": errors}


async def retrieve_news(
    state: RecommendationState,
    vector_store: NewsVectorStore | None,
    embedder=None,
) -> dict:
    """Retrieve relevant news articles from the vector store via RAG."""
    symbol = state["symbol"]
    errors = list(state.get("errors", []))

    if not vector_store or not embedder:
        return {"news_articles": [], "errors": errors}

    try:
        # Embed the query
        query_text = f"{symbol} stock analysis news recent"
        query_embedding = await embedder.embed(query_text)

        # Search vector store
        results = vector_store.search(
            query_embedding=query_embedding,
            symbol=symbol,
            n_results=5,
        )

        articles = [r.model_dump() for r in results]
        return {"news_articles": articles, "errors": errors}
    except Exception as e:
        errors.append(f"News retrieval failed for {symbol}: {e}")
        return {"news_articles": [], "errors": errors}


async def analyze_technicals(
    state: RecommendationState,
    client: AsyncAnthropic,
    model: str,
) -> dict:
    """Analyze price action and technical indicators using Claude."""
    quote = state.get("quote")
    symbol = state["symbol"]
    errors = list(state.get("errors", []))

    if not quote or not quote.get("price"):
        return {
            "technical_analysis": f"Technical analysis unavailable for {symbol} — no price data.",
            "errors": errors,
        }

    prompt = f"""Analyze the following market data for {symbol}.
Provide a brief technical assessment.
Focus on: price position within 52-week range, momentum, and key levels.
Keep it to 3-4 sentences.

Market Data:
- Price: ${quote.get("price", "N/A")}
- Day Change: {quote.get("change_percent", "N/A")}%
- Day Range: ${quote.get("day_low", "N/A")} — ${quote.get("day_high", "N/A")}
- 52-Week Range: ${quote.get("week_52_low", "N/A")} — ${quote.get("week_52_high", "N/A")}
- Market Cap: ${quote.get("market_cap", "N/A")}"""

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"technical_analysis": response.content[0].text, "errors": errors}
    except Exception as e:
        errors.append(f"Technical analysis failed: {e}")
        return {"technical_analysis": "Technical analysis unavailable.", "errors": errors}


async def analyze_fundamentals(
    state: RecommendationState,
    client: AsyncAnthropic,
    model: str,
) -> dict:
    """Analyze news and fundamental context using Claude."""
    news_articles = state.get("news_articles", [])
    symbol = state["symbol"]
    errors = list(state.get("errors", []))

    news_context = "No recent news available."
    if news_articles:
        headlines = []
        for a in news_articles[:5]:
            headline = a.get("headline", "")
            source = a.get("source", "")
            headlines.append(f"- {headline} ({source})")
        news_context = "\n".join(headlines)

    prompt = f"""Analyze the following recent news for {symbol}.
Provide a fundamental assessment.
Focus on: key themes, sentiment, and potential stock price impact.
Keep it to 3-4 sentences.

Recent News:
{news_context}"""

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"fundamental_context": response.content[0].text, "errors": errors}
    except Exception as e:
        errors.append(f"Fundamental analysis failed: {e}")
        return {"fundamental_context": "Fundamental analysis unavailable.", "errors": errors}


async def assess_portfolio_impact(
    state: RecommendationState,
    client: AsyncAnthropic,
    model: str,
) -> dict:
    """Assess how the symbol fits within the current portfolio."""
    symbol = state["symbol"]
    portfolio_summary = state.get("portfolio_summary")
    errors = list(state.get("errors", []))

    if not portfolio_summary:
        return {
            "portfolio_impact": "Portfolio impact assessment unavailable — no portfolio data.",
            "errors": errors,
        }

    allocation = portfolio_summary.get("allocation", [])
    alloc_text = "\n".join(
        f"- {a['symbol']}: {a['pct_of_portfolio']:.1f}%" for a in allocation[:10]
    )

    prompt = f"""Assess how adding or adjusting a position in {symbol} would impact this portfolio.
Consider: concentration risk, diversification, and alignment with portfolio balance.
Keep it to 3-4 sentences.

Current Portfolio Allocation:
{alloc_text}
Total Value: ${portfolio_summary.get("total_value", 0):,.2f}
Total Gain: {portfolio_summary.get("gain_pct", 0):.1f}%"""

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"portfolio_impact": response.content[0].text, "errors": errors}
    except Exception as e:
        errors.append(f"Portfolio impact assessment failed: {e}")
        return {"portfolio_impact": "Portfolio impact unavailable.", "errors": errors}


async def generate_recommendation(
    state: RecommendationState,
    client: AsyncAnthropic,
    model: str,
) -> dict:
    """Generate the final trade recommendation based on all analysis."""
    symbol = state["symbol"]
    errors = list(state.get("errors", []))

    technical = state.get("technical_analysis", "Not available.")
    fundamental = state.get("fundamental_context", "Not available.")
    impact = state.get("portfolio_impact", "Not available.")

    prompt = f"""Based on the following analysis for {symbol}, provide a trade recommendation.

TECHNICAL ANALYSIS:
{technical}

FUNDAMENTAL ANALYSIS:
{fundamental}

PORTFOLIO IMPACT:
{impact}

Respond in this exact JSON format:
{{
    "action": "BUY" or "SELL" or "HOLD" or "WATCH",
    "confidence": "HIGH" or "MEDIUM" or "LOW",
    "reasoning": "2-3 sentence explanation",
    "risk_factors": ["risk 1", "risk 2", "risk 3"]
}}

Only output the JSON, nothing else."""

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        # Parse JSON from response (handle potential markdown wrapping)
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        rec = json.loads(text)

        return {
            "action": rec.get("action", "HOLD"),
            "confidence": rec.get("confidence", "LOW"),
            "reasoning": rec.get("reasoning", ""),
            "risk_factors": rec.get("risk_factors", []),
            "errors": errors,
        }
    except Exception as e:
        errors.append(f"Recommendation generation failed: {e}")
        return {
            "action": "HOLD",
            "confidence": "LOW",
            "reasoning": f"Unable to generate recommendation: {e}",
            "risk_factors": [],
            "errors": errors,
        }


def format_recommendation(state: RecommendationState) -> dict:
    """Format the recommendation into a Telegram-friendly message."""
    symbol = state["symbol"]
    action = state.get("action", "HOLD")
    confidence = state.get("confidence", "LOW")
    reasoning = state.get("reasoning", "No analysis available.")
    risk_factors = state.get("risk_factors", [])
    quote = state.get("quote", {})

    price_str = f"${quote.get('price', 0):,.2f}" if quote and quote.get("price") else "N/A"
    change_str = ""
    if quote and quote.get("change_percent") is not None:
        pct = quote["change_percent"]
        sign = "+" if pct >= 0 else ""
        change_str = f" ({sign}{pct:.1f}%)"

    # Action emoji
    action_emoji = {"BUY": "BUY", "SELL": "SELL", "HOLD": "HOLD", "WATCH": "WATCH"}.get(
        action, action
    )

    lines = [
        f"*Trade Recommendation: {symbol}*",
        "",
        f"Action: *{action_emoji}* (Confidence: {confidence})",
        f"Price: {price_str}{change_str}",
        "",
        f"*Analysis:*\n{reasoning}",
    ]

    if risk_factors:
        lines.append("")
        lines.append("*Risk Factors:*")
        for rf in risk_factors[:5]:
            lines.append(f"  - {rf}")

    errors = state.get("errors", [])
    if errors:
        lines.append("")
        lines.append(f"_Note: {len(errors)} issue(s) during analysis_")

    return {"recommendation_text": "\n".join(lines)}
