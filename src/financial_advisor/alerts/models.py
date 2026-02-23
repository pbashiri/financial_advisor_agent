"""Pydantic models for alert configuration and triggered alerts."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AlertType(str, Enum):
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    DRIFT = "drift"
    SENTIMENT = "sentiment"


class AlertConfig(BaseModel):
    """A configured alert rule."""

    id: int | None = None
    alert_type: AlertType
    symbol: str | None = None  # None for portfolio-wide alerts (drift)
    threshold: float
    enabled: bool = True
    created_at: datetime | None = None
    notes: str = ""

    @property
    def description(self) -> str:
        if self.alert_type == AlertType.PRICE_ABOVE:
            return f"{self.symbol} price above ${self.threshold:.2f}"
        elif self.alert_type == AlertType.PRICE_BELOW:
            return f"{self.symbol} price below ${self.threshold:.2f}"
        elif self.alert_type == AlertType.DRIFT:
            return f"Allocation drift > {self.threshold:.1f}%"
        elif self.alert_type == AlertType.SENTIMENT:
            return f"{self.symbol} sentiment below {self.threshold:.1f}"
        return f"{self.alert_type.value}: {self.threshold}"


class Alert(BaseModel):
    """A triggered alert instance."""

    id: int | None = None
    config_id: int
    triggered_at: datetime = Field(default_factory=datetime.now)
    message: str
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
