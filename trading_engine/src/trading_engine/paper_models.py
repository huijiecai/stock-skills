from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PaperPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    buy_lot_size: int = Field(default=100, gt=0)
    max_single_position_pct: Decimal = Field(default=Decimal("30"), gt=0, le=100)
    max_gross_exposure_pct: Decimal = Field(default=Decimal("95"), gt=0, le=100)
    policy_version: str = "paper-main-board-v1"


class PaperRuleCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    passed: bool
    message: str


class PaperOrder(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    execution_id: str
    judgment_id: str
    proposal_index: int = Field(ge=0)
    account_id: str
    account_name: str
    snapshot_id: str
    context_id: str
    code: str = Field(pattern=r"^\d{6}$")
    side: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0)
    price: Decimal = Field(gt=0, decimal_places=2)
    notional: Decimal = Field(gt=0, decimal_places=2)
    trade_date: date
    status: Literal["filled", "rejected"]
    rejection_reason: str | None = None
    proposal_json: str
    created_at: datetime


class PaperFill(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    order_id: str
    account_id: str
    account_name: str
    code: str = Field(pattern=r"^\d{6}$")
    side: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0)
    price: Decimal = Field(gt=0, decimal_places=2)
    notional: Decimal = Field(gt=0, decimal_places=2)
    cash_before: Decimal = Field(ge=0, decimal_places=2)
    cash_after: Decimal = Field(ge=0, decimal_places=2)
    position_quantity_before: int = Field(ge=0)
    position_quantity_after: int = Field(ge=0)
    sellable_before: int = Field(ge=0)
    sellable_after: int = Field(ge=0)
    average_cost_before: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    average_cost_after: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    filled_at: datetime
    created_at: datetime


class PaperDecisionEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    execution_id: str
    judgment_id: str
    proposal_index: int = Field(ge=0)
    code: str = Field(pattern=r"^\d{6}$")
    action: Literal["WAIT", "RESEARCH", "BUY", "SELL"]
    status: Literal["skipped", "rejected", "filled"]
    trade_date: date
    reason: str
    order_id: str | None = None
    created_at: datetime


class PaperExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    account_id: str
    account_name: str
    judgment_id: str
    context_id: str
    snapshot_id: str
    policy: PaperPolicy
    status: Literal["completed"]
    events: tuple[PaperDecisionEvent, ...]
    orders: tuple[PaperOrder, ...]
    fills: tuple[PaperFill, ...]
    checks: dict[str, tuple[PaperRuleCheck, ...]]
    created_at: datetime
    completed_at: datetime


class PaperOrderAudit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order: PaperOrder
    checks: tuple[PaperRuleCheck, ...]
    fill: PaperFill | None
    valid: bool
    issues: tuple[str, ...]


class PaperAccountAudit(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str
    account_name: str
    orders: int = Field(ge=0)
    fills: int = Field(ge=0)
    valid: bool
    issues: tuple[str, ...]


class PaperReportPaths(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: str
    trades: str
    daily: str
