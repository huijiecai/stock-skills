from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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
