"""Portfolio analytics: returns, allocation, and risk metrics."""

from datetime import datetime, timezone

from ..market_data import QuoteSnapshot
from .models import AllocationItem, Holding, HoldingWithValue, PortfolioSummary


def calculate_summary(
    holdings: list[Holding], quotes: dict[str, QuoteSnapshot]
) -> PortfolioSummary:
    """Calculate full portfolio summary from holdings and live quotes."""
    enriched: list[HoldingWithValue] = []
    total_value = 0.0
    total_cost = 0.0

    for h in holdings:
        q = quotes.get(h.symbol)
        current_price = q.price if q and q.price is not None else None
        current_value = current_price * h.shares if current_price is not None else None
        total_hold_cost = h.cost_basis * h.shares

        gain_loss = (current_value - total_hold_cost) if current_value is not None else None
        gain_loss_pct = (
            ((current_value - total_hold_cost) / total_hold_cost * 100)
            if current_value is not None and total_hold_cost > 0
            else None
        )

        enriched.append(HoldingWithValue(
            symbol=h.symbol,
            shares=h.shares,
            cost_basis=h.cost_basis,
            account_type=h.account_type,
            notes=h.notes,
            current_price=current_price,
            current_value=current_value,
            total_cost=total_hold_cost,
            gain_loss=gain_loss,
            gain_loss_pct=gain_loss_pct,
            day_change_pct=q.change_percent if q else None,
        ))

        if current_value is not None:
            total_value += current_value
        total_cost += total_hold_cost

    total_gain = total_value - total_cost
    gain_pct = (total_gain / total_cost * 100) if total_cost > 0 else 0.0

    allocation = get_allocation(enriched, total_value, quotes)

    return PortfolioSummary(
        total_value=total_value,
        total_cost=total_cost,
        total_gain=total_gain,
        gain_pct=gain_pct,
        holdings=enriched,
        allocation=allocation,
        as_of=datetime.now(timezone.utc),
    )


def get_allocation(
    holdings: list[HoldingWithValue],
    total_value: float,
    quotes: dict[str, QuoteSnapshot],
) -> list[AllocationItem]:
    """Compute allocation breakdown as percentage of portfolio."""
    items: list[AllocationItem] = []
    for h in holdings:
        if h.current_value is None or h.current_value <= 0:
            continue
        q = quotes.get(h.symbol)
        name = (q.name if q else None) or h.symbol
        pct = (h.current_value / total_value * 100) if total_value > 0 else 0.0
        items.append(AllocationItem(
            symbol=h.symbol,
            name=name,
            value=h.current_value,
            pct_of_portfolio=round(pct, 2),
            account_type=h.account_type,
        ))
    return sorted(items, key=lambda x: x.pct_of_portfolio, reverse=True)


def format_portfolio_summary(summary: PortfolioSummary) -> str:
    """Format portfolio summary as Telegram markdown."""
    sign = "+" if summary.total_gain >= 0 else ""
    lines = [
        "*Portfolio Summary*\n",
        f"*Total Value:* ${summary.total_value:,.2f}",
        f"*Total Cost:* ${summary.total_cost:,.2f}",
        f"*Total P/L:* {sign}${summary.total_gain:,.2f} ({sign}{summary.gain_pct:.2f}%)",
        "",
        "*Holdings*",
    ]

    for h in summary.holdings:
        if h.current_value is not None:
            g_sign = "+" if (h.gain_loss or 0) >= 0 else ""
            day_str = ""
            if h.day_change_pct is not None:
                d_sign = "+" if h.day_change_pct >= 0 else ""
                day_str = f" | Day: {d_sign}{h.day_change_pct:.2f}%"
            lines.append(
                f"  *{h.symbol}* — ${h.current_value:,.2f} "
                f"({g_sign}${h.gain_loss:,.2f} / {g_sign}{h.gain_loss_pct:.1f}%){day_str}"
            )
        else:
            lines.append(f"  *{h.symbol}* — price unavailable")

    lines.append("")
    lines.append("*Allocation*")
    for item in summary.allocation:
        lines.append(f"  {item.symbol}: {item.pct_of_portfolio:.1f}%")

    lines.append(
        f"\n_Updated {summary.as_of.strftime('%H:%M UTC')}_"
    )
    return "\n".join(lines)
