"""Tests for the alerts engine: models, storage, checker, and engine."""

from datetime import datetime
from pathlib import Path

from financial_advisor.alerts.checker import AlertChecker
from financial_advisor.alerts.models import Alert, AlertConfig, AlertType
from financial_advisor.alerts.storage import AlertStorage
from financial_advisor.market_data import QuoteSnapshot
from financial_advisor.portfolio.models import AllocationItem, PortfolioSummary

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _quote(symbol: str, price: float, change_pct: float = 0.0) -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol=symbol,
        name=symbol,
        price=price,
        change=price * change_pct / 100,
        change_percent=change_pct,
        day_high=price,
        day_low=price,
        week_52_high=price * 1.2,
        week_52_low=price * 0.8,
        market_cap=None,
    )


def _summary(allocations: list[tuple[str, float]]) -> PortfolioSummary:
    """Create a PortfolioSummary with given (symbol, pct) allocations."""
    alloc = [
        AllocationItem(symbol=s, name=s, value=1000, pct_of_portfolio=p, account_type="brokerage")
        for s, p in allocations
    ]
    total = sum(a.value for a in alloc)
    return PortfolioSummary(
        total_value=total,
        total_cost=total * 0.9,
        total_gain=total * 0.1,
        gain_pct=10.0,
        holdings=[],
        allocation=alloc,
        as_of=datetime.now(),
    )


# ---------------------------------------------------------------------------
# AlertChecker tests
# ---------------------------------------------------------------------------


def test_price_above_triggers():
    """Price above alert fires when price exceeds threshold."""
    checker = AlertChecker()
    config = AlertConfig(id=1, alert_type=AlertType.PRICE_ABOVE, symbol="AAPL", threshold=200.0)
    quote = _quote("AAPL", 205.43, change_pct=2.7)

    alert = checker.check_price_alert(config, quote)
    assert alert is not None
    assert alert.config_id == 1
    assert "above" in alert.message
    assert "$200.00" in alert.message
    assert "$205.43" in alert.message


def test_price_above_no_trigger():
    """Price above alert does not fire when price is below threshold."""
    checker = AlertChecker()
    config = AlertConfig(id=1, alert_type=AlertType.PRICE_ABOVE, symbol="AAPL", threshold=200.0)
    quote = _quote("AAPL", 195.0)

    assert checker.check_price_alert(config, quote) is None


def test_price_below_triggers():
    """Price below alert fires when price drops below threshold."""
    checker = AlertChecker()
    config = AlertConfig(id=2, alert_type=AlertType.PRICE_BELOW, symbol="VOO", threshold=350.0)
    quote = _quote("VOO", 340.0, change_pct=-2.0)

    alert = checker.check_price_alert(config, quote)
    assert alert is not None
    assert "below" in alert.message


def test_price_below_no_trigger():
    """Price below alert does not fire when price is above threshold."""
    checker = AlertChecker()
    config = AlertConfig(id=2, alert_type=AlertType.PRICE_BELOW, symbol="VOO", threshold=350.0)
    quote = _quote("VOO", 360.0)

    assert checker.check_price_alert(config, quote) is None


def test_price_alert_with_no_data():
    """Price alert returns None when quote has no price."""
    checker = AlertChecker()
    config = AlertConfig(id=1, alert_type=AlertType.PRICE_ABOVE, symbol="AAPL", threshold=200.0)
    quote = QuoteSnapshot(
        symbol="AAPL",
        name="AAPL",
        price=None,
        change=None,
        change_percent=None,
        day_high=None,
        day_low=None,
        week_52_high=None,
        week_52_low=None,
        market_cap=None,
        error="No data",
    )

    assert checker.check_price_alert(config, quote) is None


def test_drift_alert_triggers():
    """Drift alert fires when allocation deviates beyond threshold."""
    checker = AlertChecker()
    config = AlertConfig(id=3, alert_type=AlertType.DRIFT, threshold=5.0)
    summary = _summary([("AAPL", 60.0), ("MSFT", 25.0), ("VOO", 15.0)])

    # With equal-weight targets (33.3% each), AAPL at 60% drifts 26.7%
    alert = checker.check_drift_alert(config, summary)
    assert alert is not None
    assert "AAPL" in alert.message
    assert "drift" in alert.message.lower()


def test_drift_alert_within_tolerance():
    """Drift alert does not fire when allocations are within threshold."""
    checker = AlertChecker()
    config = AlertConfig(id=3, alert_type=AlertType.DRIFT, threshold=50.0)
    summary = _summary([("AAPL", 35.0), ("MSFT", 33.0), ("VOO", 32.0)])

    assert checker.check_drift_alert(config, summary) is None


def test_drift_alert_with_custom_targets():
    """Drift alert uses custom target allocations when provided."""
    checker = AlertChecker()
    config = AlertConfig(id=3, alert_type=AlertType.DRIFT, threshold=5.0)
    summary = _summary([("AAPL", 60.0), ("MSFT", 25.0), ("VOO", 15.0)])

    targets = {"AAPL": 50.0, "MSFT": 30.0, "VOO": 20.0}
    alert = checker.check_drift_alert(config, summary, target_allocations=targets)
    assert alert is not None
    assert "AAPL" in alert.message  # 60% vs 50% target = 10% drift


# ---------------------------------------------------------------------------
# AlertStorage tests
# ---------------------------------------------------------------------------


async def test_storage_add_and_list(tmp_path: Path):
    """Add a config and retrieve it."""
    storage = AlertStorage(tmp_path / "alerts.db")
    await storage.initialize()

    config = AlertConfig(alert_type=AlertType.PRICE_ABOVE, symbol="AAPL", threshold=200.0)
    config_id = await storage.add_config(config)
    assert config_id > 0

    configs = await storage.get_configs()
    assert len(configs) == 1
    assert configs[0].symbol == "AAPL"
    assert configs[0].threshold == 200.0

    await storage.close()


async def test_storage_remove_config(tmp_path: Path):
    """Remove a config by ID."""
    storage = AlertStorage(tmp_path / "alerts.db")
    await storage.initialize()

    config_id = await storage.add_config(
        AlertConfig(alert_type=AlertType.PRICE_BELOW, symbol="VOO", threshold=350.0)
    )
    assert await storage.remove_config(config_id) is True
    assert await storage.remove_config(config_id) is False  # already removed

    configs = await storage.get_configs()
    assert len(configs) == 0

    await storage.close()


async def test_storage_toggle_config(tmp_path: Path):
    """Toggle a config enabled/disabled."""
    storage = AlertStorage(tmp_path / "alerts.db")
    await storage.initialize()

    config_id = await storage.add_config(
        AlertConfig(alert_type=AlertType.PRICE_ABOVE, symbol="AAPL", threshold=200.0)
    )

    await storage.toggle_config(config_id, enabled=False)
    enabled = await storage.get_configs(enabled_only=True)
    assert len(enabled) == 0

    await storage.toggle_config(config_id, enabled=True)
    enabled = await storage.get_configs(enabled_only=True)
    assert len(enabled) == 1

    await storage.close()


async def test_storage_record_and_acknowledge(tmp_path: Path):
    """Record a triggered alert and acknowledge it."""
    storage = AlertStorage(tmp_path / "alerts.db")
    await storage.initialize()

    config_id = await storage.add_config(
        AlertConfig(alert_type=AlertType.PRICE_ABOVE, symbol="AAPL", threshold=200.0)
    )

    alert = Alert(config_id=config_id, message="AAPL above $200")
    alert_id = await storage.record_alert(alert)
    assert alert_id > 0

    assert await storage.acknowledge_alert(alert_id) is True

    await storage.close()


async def test_storage_dedup_check(tmp_path: Path):
    """Recently triggered alerts are detected for dedup."""
    storage = AlertStorage(tmp_path / "alerts.db")
    await storage.initialize()

    config_id = await storage.add_config(
        AlertConfig(alert_type=AlertType.PRICE_ABOVE, symbol="AAPL", threshold=200.0)
    )

    assert await storage.was_recently_triggered(config_id) is False

    await storage.record_alert(Alert(config_id=config_id, message="test"))
    assert await storage.was_recently_triggered(config_id) is True

    await storage.close()


async def test_storage_recent_alerts(tmp_path: Path):
    """Get recently triggered alerts."""
    storage = AlertStorage(tmp_path / "alerts.db")
    await storage.initialize()

    config_id = await storage.add_config(
        AlertConfig(alert_type=AlertType.PRICE_ABOVE, symbol="AAPL", threshold=200.0)
    )
    await storage.record_alert(Alert(config_id=config_id, message="alert 1"))
    await storage.record_alert(Alert(config_id=config_id, message="alert 2"))

    recent = await storage.get_recent_alerts(hours=24)
    assert len(recent) == 2

    await storage.close()


# ---------------------------------------------------------------------------
# AlertConfig model tests
# ---------------------------------------------------------------------------


def test_alert_config_description():
    """AlertConfig.description generates human-readable text."""
    c1 = AlertConfig(id=1, alert_type=AlertType.PRICE_ABOVE, symbol="AAPL", threshold=200.0)
    assert "AAPL" in c1.description
    assert "above" in c1.description

    c2 = AlertConfig(id=2, alert_type=AlertType.DRIFT, threshold=5.0)
    assert "drift" in c2.description.lower()
