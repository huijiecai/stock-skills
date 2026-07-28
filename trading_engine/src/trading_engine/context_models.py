from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trading_engine.models import (
    AccountState,
    PositionState,
    RiskFactorState,
    ThesisState,
    TradePlanState,
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
    pre_close: Decimal = Field(ge=0)
    change_pct: Decimal
    volume: int = Field(ge=0)
    amount: Decimal = Field(ge=0)
    open: Decimal = Field(ge=0)
    high: Decimal = Field(ge=0)
    low: Decimal = Field(ge=0)
    path: "PricePathContext | None" = None


class PricePathContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Literal["minute_bars", "session_quote"]
    bar_count: int = Field(ge=0)
    first_bar_time: datetime | None = None
    latest_bar_time: datetime | None = None
    change_from_open_pct: Decimal | None = None
    rebound_from_low_pct: Decimal | None = None
    drawdown_from_high_pct: Decimal | None = None
    ten_minute_change_pct: Decimal | None = None
    dipped_below_pre_close: bool
    recovered_above_pre_close: bool
    limit_up_like: bool
    one_word_limit_like: bool


class PoolMemberSignalContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=r"^\d{6}$")
    role: Literal["direct", "research"]
    relationship: Literal[
        "direct", "volume", "adjacent", "cost_pressure", "research"
    ]
    tradable: bool
    change_pct: Decimal
    amount: Decimal = Field(ge=0)
    change_rank: int = Field(ge=1)
    amount_rank: int = Field(ge=1)
    is_up: bool
    is_strong: bool
    is_limit_up: bool
    path: PricePathContext


class PoolMetricsContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    registered_count: int = Field(ge=0)
    quoted_count: int = Field(ge=0)
    up_count: int = Field(ge=0)
    down_count: int = Field(ge=0)
    flat_count: int = Field(ge=0)
    strong_count: int = Field(ge=0)
    limit_up_count: int = Field(ge=0)
    tradable_count: int = Field(ge=0)
    tradable_up_count: int = Field(ge=0)
    breadth_pct: Decimal = Field(ge=0, le=100)
    leader_codes: tuple[str, ...]


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
    member_signals: tuple[PoolMemberSignalContext, ...] = Field(default_factory=tuple)
    metrics: PoolMetricsContext | None = None
    missing_codes: tuple[str, ...]
    coverage_pct: Decimal = Field(ge=0, le=100)


class RiskExposureContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    factor: RiskFactorState
    position_codes: tuple[str, ...]
    market_value: Decimal = Field(ge=0, decimal_places=2)
    exposure_pct: Decimal = Field(ge=0)
    limit_breached: bool


class StrategyRulesContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    main_board_prefixes: tuple[str, ...]
    buy_lot_size: int = Field(gt=0)
    max_theme_exposure_pct: Decimal = Field(ge=0, le=100)
    default_shared_risk_limit_pct: Decimal = Field(ge=0, le=100)
    max_batch_buys: int = Field(gt=0)
    no_new_positions_after: time
    sell_confirmation_points: int = Field(gt=0)
    buy_gates: tuple[str, ...]
    ranking_dimensions: tuple[str, ...]
    sell_exit_rules: tuple[str, ...]
    operating_rules: tuple[str, ...]


class TradePlanContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan: TradePlanState
    observed_times: tuple[datetime, ...]
    missing_observation_times: tuple[time, ...]
    target_quote: ContextQuote | None
    target_pool_keys: tuple[str, ...]


class HistoricalPoolObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pool_key: str
    monitoring_status: Literal["active", "dormant", "archived"]
    metrics: PoolMetricsContext
    member_signals: tuple[PoolMemberSignalContext, ...]


class HistoricalPositionObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=r"^\d{6}$")
    change_pct: Decimal
    price: Decimal = Field(gt=0)
    path: PricePathContext


class HistoricalObservationContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    as_of: datetime
    positions: tuple[HistoricalPositionObservation, ...]
    pools: tuple[HistoricalPoolObservation, ...]


class PriorDecisionContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    as_of: datetime
    code: str = Field(pattern=r"^\d{6}$")
    action: Literal["WAIT", "RESEARCH", "BUY", "SELL"]
    quantity: int | None = Field(default=None, gt=0)
    reason: str = Field(min_length=1)


class ExecutedTradeContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: str
    filled_at: datetime
    code: str = Field(pattern=r"^\d{6}$")
    side: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0)
    price: Decimal = Field(gt=0, decimal_places=2)
    notional: Decimal = Field(gt=0, decimal_places=2)
    cash_after: Decimal = Field(ge=0, decimal_places=2)
    position_quantity_after: int = Field(ge=0)
    sellable_after: int = Field(ge=0)


class MarketCandidateContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(pattern=r"^\d{6}$")
    name: str
    industry: str | None = None
    sector: str | None = None
    business: str | None = None
    price: Decimal = Field(gt=0)
    pre_close: Decimal = Field(ge=0)
    change_pct: Decimal
    amount: Decimal = Field(ge=0)
    low: Decimal = Field(ge=0)
    rebound_pct: Decimal
    limit_up: bool
    reasons: tuple[str, ...] = Field(default_factory=tuple)


class SectorLeaderContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    name: str
    block_type: Literal["concept", "style"]
    change_pct: Decimal
    amount: Decimal = Field(ge=0)
    limit_up_count: int = Field(ge=0)


class MarketIndexContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    name: str
    price: Decimal = Field(gt=0)
    pre_close: Decimal = Field(gt=0)
    change_pct: Decimal
    amount: Decimal = Field(ge=0)


class MarketDiscoveryContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    coverage_mode: Literal["registered_universe", "candidate_universe", "full_market"]
    scanned_codes: tuple[str, ...]
    universe_count: int | None = Field(default=None, ge=0)
    scanned_count: int | None = Field(default=None, ge=0)
    missing_quote_count: int | None = Field(default=None, ge=0)
    failed_batches: int | None = Field(default=None, ge=0)
    candidate_codes: tuple[str, ...] = Field(default_factory=tuple)
    candidates: tuple[MarketCandidateContext, ...] = Field(default_factory=tuple)
    top_amount: tuple[MarketCandidateContext, ...] = Field(default_factory=tuple)
    sector_leaders: tuple[SectorLeaderContext, ...] = Field(default_factory=tuple)
    indices: tuple[MarketIndexContext, ...] = Field(default_factory=tuple)
    limit_up_codes: tuple[str, ...] = Field(default_factory=tuple)
    missing_capabilities: tuple[str, ...] = Field(default_factory=tuple)


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
    trade_plans: tuple[TradePlanContext, ...] = Field(default_factory=tuple)
    observation_history: tuple[HistoricalObservationContext, ...] = Field(
        default_factory=tuple
    )
    prior_decisions: tuple[PriorDecisionContext, ...] = Field(default_factory=tuple)
    execution_history: tuple[ExecutedTradeContext, ...] = Field(default_factory=tuple)
    risk_exposures: tuple[RiskExposureContext, ...]
    evidence: tuple[CatalystEvidence, ...]
    market_discovery: MarketDiscoveryContext | None = None
    strategy_rules: StrategyRulesContext | None = None
    excluded_future_evidence_count: int = Field(ge=0)
    blockers: tuple[str, ...]
    ready_for_judgment: bool
    policy: str = "independent-context-v2"


class DecisionContextRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    context: DecisionContext
    created_at: datetime
