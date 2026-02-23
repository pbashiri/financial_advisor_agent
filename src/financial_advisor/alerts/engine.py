"""Alert engine: loads configs, checks conditions, records triggered alerts."""

import logging

from ..market_data import QuoteSnapshot, get_quote
from ..portfolio.analytics import calculate_summary
from ..portfolio.models import Holding
from .checker import AlertChecker
from .models import Alert, AlertConfig, AlertType
from .storage import AlertStorage

logger = logging.getLogger(__name__)


class AlertEngine:
    """Orchestrates alert checking across all configured rules."""

    def __init__(self, storage: AlertStorage):
        self._storage = storage
        self._checker = AlertChecker()

    async def run_check_cycle(
        self,
        holdings: list[Holding] | None = None,
        quotes: dict[str, QuoteSnapshot] | None = None,
    ) -> list[Alert]:
        """Evaluate all enabled alert configs and return newly triggered alerts.

        Skips alerts that were triggered within the last 24 hours (dedup).

        Args:
            holdings: Current portfolio holdings (needed for drift alerts).
            quotes: Pre-fetched quotes keyed by symbol. If None, fetches live.

        Returns:
            List of newly triggered Alert objects.
        """
        configs = await self._storage.get_configs(enabled_only=True)
        if not configs:
            return []

        triggered: list[Alert] = []

        for config in configs:
            try:
                # Skip if recently triggered (24h dedup)
                if await self._storage.was_recently_triggered(config.id):
                    continue

                alert = await self._evaluate_config(config, holdings, quotes)
                if alert:
                    alert_id = await self._storage.record_alert(alert)
                    alert.id = alert_id
                    triggered.append(alert)
                    logger.info("Alert triggered: config_id=%d — %s", config.id, config.description)

            except Exception as e:
                logger.error("Error checking alert config %d: %s", config.id, e)

        if triggered:
            logger.info("Check cycle: %d alerts triggered", len(triggered))
        return triggered

    async def _evaluate_config(
        self,
        config: AlertConfig,
        holdings: list[Holding] | None,
        quotes: dict[str, QuoteSnapshot] | None,
    ) -> Alert | None:
        """Evaluate a single alert config."""
        if config.alert_type in (AlertType.PRICE_ABOVE, AlertType.PRICE_BELOW):
            return await self._check_price(config, quotes)
        elif config.alert_type == AlertType.DRIFT:
            return await self._check_drift(config, holdings, quotes)
        return None

    async def _check_price(
        self,
        config: AlertConfig,
        quotes: dict[str, QuoteSnapshot] | None,
    ) -> Alert | None:
        """Evaluate a price alert."""
        if not config.symbol:
            return None

        # Use pre-fetched quote or fetch live
        if quotes and config.symbol in quotes:
            quote = quotes[config.symbol]
        else:
            quote = await get_quote(config.symbol)

        return self._checker.check_price_alert(config, quote)

    async def _check_drift(
        self,
        config: AlertConfig,
        holdings: list[Holding] | None,
        quotes: dict[str, QuoteSnapshot] | None,
    ) -> Alert | None:
        """Evaluate a drift alert."""
        if not holdings:
            return None

        # Build quotes dict if not provided
        if not quotes:
            from ..market_data import get_multiple_quotes

            fetched = await get_multiple_quotes([h.symbol for h in holdings])
            quotes = {q.symbol: q for q in fetched}

        summary = calculate_summary(holdings, quotes)
        return self._checker.check_drift_alert(config, summary)

    async def get_recent_triggered(self, hours: int = 24) -> list[Alert]:
        """Get recently triggered alerts."""
        return await self._storage.get_recent_alerts(hours=hours)

    async def acknowledge(self, alert_id: int) -> bool:
        """Acknowledge an alert."""
        return await self._storage.acknowledge_alert(alert_id)
