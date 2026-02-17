"""Pydantic models for portfolio data."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class Holding(BaseModel):
    symbol: str
    shares: float
    cost_basis: float
    account_type: str = "brokerage"
    notes: Optional[str] = None
    added_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("symbol")
    @classmethod
    def symbol_upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("shares")
    @classmethod
    def shares_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("shares must be positive")
        return v

    @field_validator("cost_basis")
    @classmethod
    def cost_basis_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("cost_basis must be positive")
        return v


class Transaction(BaseModel):
    symbol: str
    action: str  # 'BUY' or 'SELL'
    shares: float
    price: float
    fees: float = 0.0
    transacted_at: Optional[datetime] = None
    notes: Optional[str] = None

    @field_validator("action")
    @classmethod
    def action_valid(cls, v: str) -> str:
        v = v.upper()
        if v not in ("BUY", "SELL"):
            raise ValueError("action must be BUY or SELL")
        return v

    @field_validator("symbol")
    @classmethod
    def symbol_upper(cls, v: str) -> str:
        return v.strip().upper()


class HoldingWithValue(BaseModel):
    """A holding enriched with live market data."""

    symbol: str
    shares: float
    cost_basis: float
    account_type: str
    notes: Optional[str] = None
    current_price: Optional[float] = None
    current_value: Optional[float] = None
    total_cost: Optional[float] = None
    gain_loss: Optional[float] = None
    gain_loss_pct: Optional[float] = None
    day_change_pct: Optional[float] = None


class AllocationItem(BaseModel):
    symbol: str
    name: str
    value: float
    pct_of_portfolio: float
    account_type: str


class PortfolioSummary(BaseModel):
    total_value: float
    total_cost: float
    total_gain: float
    gain_pct: float
    holdings: list[HoldingWithValue]
    allocation: list[AllocationItem]
    as_of: datetime
