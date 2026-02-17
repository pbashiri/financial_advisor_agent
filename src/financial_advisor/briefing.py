"""Daily briefing: fetch market data, format sections, and generate Claude summary."""

import logging
from datetime import datetime, timezone

from .agent import FinancialAdvisorAgent
from .config import Settings
from .market_data import format_quote, get_index_quotes, get_multiple_quotes

logger = logging.getLogger(__name__)

NOTABLE_MOVE_THRESHOLD = 3.0  # percent


async def _format_holdings_section(settings: Settings) -> str:
    """Format holdings with live prices (used as fallback when API is offline)."""
    holdings = settings.user_profile.get("holdings", [])
    if not holdings:
        return ""

    holding_symbols = [h["symbol"] for h in holdings if "symbol" in h]
    if not holding_symbols:
        return ""

    quotes = await get_multiple_quotes(holding_symbols)
    quote_map = {q.symbol: q for q in quotes}
    lines = []

    for h in holdings:
        sym = h.get("symbol")
        if not sym or sym not in quote_map:
            continue
        q = quote_map[sym]
        if q.price is None:
            lines.append(f"  {sym}: Data unavailable")
            continue

        shares = h.get("shares", 0)
        cost_basis = h.get("cost_basis")
        line = format_quote(q)

        if cost_basis and shares:
            total_value = q.price * shares
            total_cost = cost_basis * shares
            gain = total_value - total_cost
            gain_pct = ((q.price - cost_basis) / cost_basis) * 100
            sign = "+" if gain >= 0 else ""
            pl = f"{sign}${gain:,.2f} ({sign}{gain_pct:.1f}%)"
            line += f"\n    {shares} shares | Cost: ${cost_basis:,.2f} | P/L: {pl}"

        lines.append(line)

    return "\n".join(lines)


async def generate_briefing(settings: Settings, agent: FinancialAdvisorAgent) -> str:
    """Generate a full daily market briefing."""
    now = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
    sections: list[str] = [f"*Daily Market Briefing — {now}*\n"]

    # Section 1: Major Indices
    indices = await get_index_quotes(settings.major_indices)
    sections.append("*Major Indices*")
    for q in indices:
        sections.append(format_quote(q))

    # Section 2: Your Holdings
    holdings_text = await _format_holdings_section(settings)
    if holdings_text:
        sections.append("\n*Your Holdings*")
        sections.append(holdings_text)

    # Section 3: Watchlist
    watchlist = settings.user_profile.get("watchlist", [])
    if watchlist:
        sections.append("\n*Watchlist*")
        watch_quotes = await get_multiple_quotes(watchlist)
        for q in watch_quotes:
            sections.append(format_quote(q))

    # Section 4: Notable Moves (>3%)
    all_quotes = []
    all_quotes.extend(indices)
    profile_holdings = settings.user_profile.get("holdings", [])
    if profile_holdings:
        holding_symbols = [h["symbol"] for h in profile_holdings if "symbol" in h]
        if holding_symbols:
            all_quotes.extend(await get_multiple_quotes(holding_symbols))
    if watchlist:
        all_quotes.extend(await get_multiple_quotes(watchlist))

    notable = [
        q
        for q in all_quotes
        if q.change_percent is not None and abs(q.change_percent) >= NOTABLE_MOVE_THRESHOLD
    ]
    if notable:
        notable.sort(key=lambda q: abs(q.change_percent or 0), reverse=True)
        sections.append("\n*Notable Moves (>3%)*")
        for q in notable:
            arrow = "+" if (q.change_percent or 0) >= 0 else ""
            sections.append(f"  {q.name} ({q.symbol}): {arrow}{q.change_percent:.2f}%")

    # Section 5: AI Market Summary
    raw_data = "\n".join(sections)
    summary = await agent.summarize(raw_data)
    sections.append(f"\n*Market Summary*\n{summary}")

    sections.append(
        "\n_Data from Yahoo Finance. This is not financial advice._"
    )

    return "\n".join(sections)
