"""Stateless alert condition evaluators."""

import logging

from ..market_data import QuoteSnapshot
from ..portfolio.models import PortfolioSummary
from .models import Alert, AlertConfig, AlertType

logger = logging.getLogger(__name__)


class AlertChecker:
    """Evaluates alert conditions against live market and portfolio data."""

    def check_price_alert(
        self,
        config: AlertConfig,
        quote: QuoteSnapshot,
    ) -> Alert | None:
        """Check a price alert (above or below) against a live quote.

        Returns an Alert if triggered, None otherwise.
        """
        if quote.price is None or quote.error:
            return None

        triggered = False
        if config.alert_type == AlertType.PRICE_ABOVE and quote.price > config.threshold:
            triggered = True
        elif config.alert_type == AlertType.PRICE_BELOW and quote.price < config.threshold:
            triggered = True

        if not triggered:
            return None

        direction = "above" if config.alert_type == AlertType.PRICE_ABOVE else "below"
        change_str = ""
        if quote.change_percent is not None:
            sign = "+" if quote.change_percent >= 0 else ""
            change_str = f" ({sign}{quote.change_percent:.1f}% today)"

        return Alert(
            config_id=config.id,
            message=(
                f"*Alert:* {config.symbol} price {direction} ${config.threshold:.2f} target\n"
                f"Current: ${quote.price:,.2f}{change_str}"
            ),
        )

    def check_drift_alert(
        self,
        config: AlertConfig,
        summary: PortfolioSummary,
        target_allocations: dict[str, float] | None = None,
    ) -> Alert | None:
        """Check if any holding's allocation deviates from target by more than threshold %.

        If no target_allocations provided, uses equal-weight as baseline.

        Returns an Alert if drift exceeds threshold, None otherwise.
        """
        if not summary.allocation or summary.total_value <= 0:
            return None

        n = len(summary.allocation)
        if n == 0:
            return None

        # Default: equal-weight target
        if not target_allocations:
            equal_pct = 100.0 / n
            target_allocations = {a.symbol: equal_pct for a in summary.allocation}

        drifts = []
        for alloc in summary.allocation:
            target = target_allocations.get(alloc.symbol, 0)
            drift = abs(alloc.pct_of_portfolio - target)
            if drift > config.threshold:
                drifts.append((alloc.symbol, alloc.pct_of_portfolio, target, drift))

        if not drifts:
            return None

        # Report the largest drift
        drifts.sort(key=lambda x: x[3], reverse=True)
        symbol, actual, target, drift = drifts[0]

        return Alert(
            config_id=config.id,
            message=(
                f"*Alert:* Allocation drift > {config.threshold:.1f}%\n"
                f"{symbol}: {actual:.1f}% actual vs {target:.1f}% target "
                f"(drift: {drift:.1f}%)"
            ),
        )
