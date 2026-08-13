from __future__ import annotations

from datetime import date, datetime, time
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
    pre_close: float = Field(ge=0)
    change_pct: float
    volume: int = Field(ge=0)
    amount: float = Field(ge=0)
    open: float = Field(ge=0)
    high: float = Field(ge=0)
    low: float = Field(ge=0)


class JudgmentContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: str
    as_of: datetime
    source: str
    quotes: tuple[LiveQuote, ...] = Field(min_length=1)
    decision_context_id: str | None = None
    decision_context_fingerprint: str | None = None
    domain_context: dict[str, Any] | None = None
    policy: str = "read-only-shadow-v1"


class JudgmentProposal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=r"^\d{6}$")
    action: Literal["WAIT", "RESEARCH", "BUY", "SELL"]
    quantity: int | None = Field(default=None, gt=0)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)
    evidence: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_trade_quantity(self) -> "JudgmentProposal":
        if self.action in {"BUY", "SELL"} and self.quantity is None:
            raise ValueError("BUY/SELL proposals require quantity")
        if self.action in {"WAIT", "RESEARCH"} and self.quantity is not None:
            raise ValueError("WAIT/RESEARCH proposals cannot include quantity")
        return self


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


class ThesisState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    title: str = Field(min_length=1)
    status: Literal[
        "draft", "active", "watch", "realized", "invalidated", "archived"
    ]
    summary: str = Field(min_length=1)
    realization_condition: str = Field(min_length=1)
    invalidation_condition: str = Field(min_length=1)
    thesis_type: Literal["continuous", "event", "realtime"] | None = None
    stage: Literal[
        "emerging", "confirmed", "accelerating", "realizing", "ended"
    ] | None = None
    catalyst_anchor: str | None = None
    transmission_chain: str | None = None
    linkage_conclusion: Literal[
        "company", "sub_industry", "end_demand", "unresolved"
    ] | None = None
    confirmation_condition: str | None = None
    bet_pct: Decimal | None = None
    created_at: datetime
    updated_at: datetime


class PositionThesisLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str
    code: str = Field(pattern=r"^\d{6}$")
    thesis_id: str
    thesis_key: str
    created_at: datetime


class WatchPoolState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1)
    thesis_id: str | None = None
    thesis_key: str | None = None
    active: bool
    monitoring_status: Literal["active", "dormant", "archived"] = "active"
    created_at: datetime
    updated_at: datetime


class WatchPoolMember(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pool_id: str
    pool_key: str
    code: str = Field(pattern=r"^\d{6}$")
    role: Literal["direct", "research"]
    tradable: bool
    relationship: Literal[
        "direct", "volume", "adjacent", "cost_pressure", "research"
    ] = "direct"
    causal_chain: str | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_research_member(self) -> "WatchPoolMember":
        if self.role == "research" and self.tradable:
            raise ValueError("research pool members cannot be tradable")
        if self.relationship in {"adjacent", "cost_pressure", "research"} and self.tradable:
            raise ValueError(
                "adjacent, cost-pressure, and research members cannot be tradable"
            )
        return self


class RiskFactorState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1)
    max_exposure_pct: Decimal = Field(ge=0, le=100, decimal_places=2)
    active: bool
    created_at: datetime
    updated_at: datetime


class PositionRiskLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str
    code: str = Field(pattern=r"^\d{6}$")
    risk_factor_id: str
    risk_factor_key: str
    created_at: datetime


class TradePlanState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    trading_date: date
    thesis_id: str
    thesis_key: str
    action: Literal["BUY", "SELL"]
    target_code: str = Field(pattern=r"^\d{6}$")
    target_name: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    priority: int = Field(ge=0)
    status: Literal["active", "triggered", "cancelled", "expired"]
    buy_point_type: Literal["confirmation", "first_board", "pullback"] | None = None
    exit_mode: Literal["expectation", "trade_confirmation"] | None = None
    risk_factor_key: str | None = None
    observation_times: tuple[time, ...] = Field(default_factory=tuple)
    required_observations: int = Field(default=1, ge=1)
    trigger_conditions: tuple[str, ...] = Field(min_length=1)
    guard_conditions: tuple[str, ...] = Field(default_factory=tuple)
    cancel_conditions: tuple[str, ...] = Field(default_factory=tuple)
    ranking_notes: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_plan_shape(self) -> "TradePlanState":
        if self.action == "BUY" and self.buy_point_type is None:
            raise ValueError("BUY plans require buy_point_type")
        if self.action == "SELL" and self.exit_mode is None:
            raise ValueError("SELL plans require exit_mode")
        if self.quantity % 100 != 0:
            raise ValueError("trade plan quantity must use 100-share board lots")
        if self.observation_times and self.required_observations > len(
            self.observation_times
        ):
            raise ValueError(
                "required_observations cannot exceed configured observation times"
            )
        return self
