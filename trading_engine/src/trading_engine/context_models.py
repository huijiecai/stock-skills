from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trading_engine.models import (
    AccountState,
    PositionState,
    RiskFactorState,
    ThesisState,
    WatchPoolMember,
    WatchPoolState,
)


class CatalystEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    thesis_id: str
    thesis_key: str
    kind: Literal["announcement", "news", "industry", "market", "other"]
    source_name: str = Field(min_length=1)
    source_url: str | None = None
    published_at: datetime
    observed_at: datetime
    summary: str = Field(min_length=1)
    stance: Literal["supports", "contradicts", "neutral"]
    reliability: Literal["low", "medium", "high"]
    created_at: datetime

    @model_validator(mode="after")
    def validate_timestamps(self) -> "CatalystEvidence":
        if self.published_at.tzinfo is None or self.observed_at.tzinfo is None:
            raise ValueError("evidence timestamps must include a timezone")
        if self.published_at > self.observed_at:
            raise ValueError("published_at cannot be later than observed_at")
        return self


class ContextQuote(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=r"^\d{6}$")
    observed_at: datetime
    price: Decimal = Field(gt=0)
    pre_close: Decimal = Field(gt=0)
    change_pct: Decimal
    volume: int = Field(ge=0)
    amount: Decimal = Field(ge=0)
    open: Decimal = Field(ge=0)
    high: Decimal = Field(ge=0)
    low: Decimal = Field(ge=0)


class PositionDecisionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    position: PositionState
    quote: ContextQuote
    market_value: Decimal = Field(ge=0, decimal_places=2)
    unrealized_pnl: Decimal = Field(decimal_places=2)
    pnl_pct: Decimal
    thesis_keys: tuple[str, ...]
    risk_factor_keys: tuple[str, ...]


class PoolDecisionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pool: WatchPoolState
    members: tuple[WatchPoolMember, ...]
    quotes: tuple[ContextQuote, ...]
    missing_codes: tuple[str, ...]
    coverage_pct: Decimal = Field(ge=0, le=100)


class RiskExposureContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    factor: RiskFactorState
    position_codes: tuple[str, ...]
    market_value: Decimal = Field(ge=0, decimal_places=2)
    exposure_pct: Decimal = Field(ge=0)
    limit_breached: bool


class DecisionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    market_snapshot_id: str
    account: AccountState
    as_of: datetime
    market_source: str
    cash: Decimal = Field(ge=0, decimal_places=2)
    positions_market_value: Decimal = Field(ge=0, decimal_places=2)
    total_assets: Decimal = Field(ge=0, decimal_places=2)
    positions: tuple[PositionDecisionContext, ...]
    theses: tuple[ThesisState, ...]
    pools: tuple[PoolDecisionContext, ...]
    risk_exposures: tuple[RiskExposureContext, ...]
    evidence: tuple[CatalystEvidence, ...]
    excluded_future_evidence_count: int = Field(ge=0)
    blockers: tuple[str, ...]
    ready_for_judgment: bool
    policy: str = "independent-context-v1"


class DecisionContextRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    context: DecisionContext
    created_at: datetime
