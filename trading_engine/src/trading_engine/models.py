from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: datetime
    source: str
    payload: dict[str, Any] = Field(default_factory=dict)


class TradeProposal(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: Literal["WAIT", "RESEARCH", "BUY", "SELL", "HOLD"]
    code: str | None = None
    quantity: int | None = Field(default=None, gt=0)
    reason: str


class ExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    accepted: bool
    message: str
    order_id: str | None = None


class AstockHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    available: bool
    binary: Path
    version: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    error: str | None = None


class MinuteBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = Field(ge=0)
    amount: float = Field(ge=0)


class ReplayRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    trading_date: date
    codes: tuple[str, ...]
    current_time: datetime
    status: Literal["running", "paused", "completed", "failed"]
    created_at: datetime
    updated_at: datetime


class LiveQuote(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    price: float = Field(gt=0)
    pre_close: float = Field(gt=0)
    change_pct: float
    volume: int = Field(ge=0)
    amount: float = Field(ge=0)
    open: float = Field(ge=0)
    high: float = Field(ge=0)
    low: float = Field(ge=0)


class LiveSnapshotRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    snapshot: MarketSnapshot


class JudgmentContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: str
    as_of: datetime
    source: str
    quotes: tuple[LiveQuote, ...] = Field(min_length=1)
    policy: str = "read-only-shadow-v1"


class JudgmentProposal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=r"^\d{6}$")
    action: Literal["WAIT", "RESEARCH", "BUY", "SELL"]
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    evidence: tuple[str, ...] = Field(default_factory=tuple)


class JudgmentReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: str
    as_of: datetime
    provider: str
    model: str
    proposals: tuple[JudgmentProposal, ...] = Field(min_length=1)
    limitations: tuple[str, ...] = Field(default_factory=tuple)


class JudgmentRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    snapshot_id: str
    provider: str
    model: str
    status: Literal["completed", "failed"]
    attempts: int = Field(ge=1)
    input_context: JudgmentContext
    report: JudgmentReport | None = None
    error: str | None = None
    created_at: datetime


class AccountState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str = Field(min_length=1)
    initial_cash: Decimal = Field(ge=0, decimal_places=2)
    cash: Decimal = Field(ge=0, decimal_places=2)
    cooldown: bool = False
    created_at: datetime
    updated_at: datetime


class PositionState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str
    code: str = Field(pattern=r"^\d{6}$")
    name: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    sellable_quantity: int = Field(ge=0)
    average_cost: Decimal = Field(gt=0, decimal_places=2)
    bought_on: date
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_sellable_quantity(self) -> "PositionState":
        if self.sellable_quantity > self.quantity:
            raise ValueError("sellable_quantity cannot exceed quantity")
        return self
